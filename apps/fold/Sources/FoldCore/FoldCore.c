#include "FoldCore.h"
#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

static const double tau = 6.2831853071795864769;
static double clamp(double x, double lo, double hi) { return fmin(hi, fmax(lo, x)); }
static double finite_or(double x, double fallback) { return isfinite(x) ? x : fallback; }

bool fold_decode_report(const uint8_t *bytes, size_t length, double *angle) {
    if (!bytes || !angle || length < 3 || bytes[0] != 1) return false;
    unsigned raw = (unsigned)bytes[1] | ((unsigned)bytes[2] << 8);
    if (raw > 180) return false; // A clamshell MacBook cannot have a >180 degree hinge opening.
    *angle = (double)raw;
    return true;
}

double fold_progress(double angle, double clear_angle) {
    if (!isfinite(angle)) return 0; // Invalid hardware data must clear the effect.
    double clear = clamp(finite_or(clear_angle, 105), 65, 135);
    double t = clamp((clear - angle) / (clear - 15), 0, 1);
    return t * t * (3 - 2 * t);
}

void fold_motion_reset(FoldMotion *m) { if (m) memset(m, 0, sizeof(*m)); }

FoldReading fold_motion_update(FoldMotion *m, double raw, double time, double clear) {
    FoldReading out = {0};
    if (!m || !isfinite(raw) || raw < 0 || raw > 180 || !isfinite(time)) return out;
    double dt = time - m->last_time;
    if (!m->initialized || dt <= 0 || dt > 0.5) {
        m->angle = m->last_raw = raw;
        m->last_time = time;
        m->velocity = m->still_time = 0;
        m->initialized = true;
        m->was_folded = false; // Never click from stale pre-sleep history.
    } else {
        double delta = raw - m->last_raw;
        double alpha = 1 - exp(-dt / 0.045);
        m->angle += (raw - m->angle) * alpha;
        if (fabs(delta) >= 0.4) {
            m->velocity += (clamp(delta / dt, -360, 360) - m->velocity) * (1 - exp(-dt / 0.055));
            m->still_time = 0;
        } else {
            m->still_time += dt;
            m->velocity *= exp(-dt / 0.045);
            if (m->still_time > 0.12) m->velocity = 0;
        }
        m->last_raw = raw;
        m->last_time = time;
    }
    out.angle = m->angle;
    out.velocity = m->velocity;
    out.progress = fold_progress(m->angle, clear);
    if (out.progress > 0.03) m->was_folded = true;
    if (m->was_folded && m->angle >= clear - 0.3) {
        out.opened = true;
        m->was_folded = false;
    }
    return out;
}

size_t fold_mesh_count(int columns, int rows) {
    if (columns < 1 || rows < 1 || columns > 256 || rows > 256) return 0;
    return (size_t)columns * (size_t)rows * 6;
}

static FoldVertex vertex(float u, float v, float p, float perspective) {
    float h = 1 - v;
    float width = 1 - 0.38f * p * perspective * h * h;
    float dest_x = 0.5f + (u - 0.5f) * width;
    // A curved sheet anchored at the hinge. The derivative stays positive for p in [0,1].
    float dest_y = 1 - h * (1 - 0.72f * p) - 0.07f * p * sinf((float)(tau / 2) * h);
    return (FoldVertex){ 2 * dest_x - 1, 1 - 2 * dest_y, u, v };
}

size_t fold_make_mesh(FoldVertex *out, size_t capacity, int columns, int rows,
                      float progress, float perspective) {
    size_t count = fold_mesh_count(columns, rows);
    if (!out || count == 0 || capacity < count) return 0;
    float p = (float)clamp(finite_or(progress, 0), 0, 1);
    float s = (float)clamp(finite_or(perspective, 1), 0, 1);
    size_t n = 0;
    for (int y = 0; y < rows; y++) for (int x = 0; x < columns; x++) {
        float u0 = (float)x / columns, u1 = (float)(x + 1) / columns;
        float v0 = (float)y / rows, v1 = (float)(y + 1) / rows;
        FoldVertex a = vertex(u0, v0, p, s), b = vertex(u1, v0, p, s);
        FoldVertex c = vertex(u0, v1, p, s), d = vertex(u1, v1, p, s);
        out[n++] = a; out[n++] = c; out[n++] = b;
        out[n++] = b; out[n++] = c; out[n++] = d;
    }
    return n;
}

struct FoldAudio {
    _Atomic float target_progress, target_velocity, target_volume;
    _Atomic int mode;
    _Atomic bool click;
    double sample_rate, phase, phase2, gain, frequency, click_age;
    uint32_t random;
};

FoldAudio *fold_audio_create(double sample_rate) {
    if (!isfinite(sample_rate) || sample_rate < 8000 || sample_rate > 192000) return NULL;
    FoldAudio *a = calloc(1, sizeof(*a));
    if (!a) return NULL;
    a->sample_rate = sample_rate;
    a->frequency = 180;
    a->click_age = 1;
    a->random = 0xC0FFEEu;
    atomic_init(&a->target_progress, 0); atomic_init(&a->target_velocity, 0);
    atomic_init(&a->target_volume, 0); atomic_init(&a->mode, 0); atomic_init(&a->click, false);
    return a;
}
void fold_audio_destroy(FoldAudio *a) { free(a); }
void fold_audio_set(FoldAudio *a, double p, double velocity, double volume, int mode) {
    if (!a) return;
    atomic_store_explicit(&a->target_progress, (float)clamp(finite_or(p, 0), 0, 1), memory_order_relaxed);
    atomic_store_explicit(&a->target_velocity, (float)clamp(finite_or(velocity, 0), -360, 360), memory_order_relaxed);
    atomic_store_explicit(&a->target_volume, (float)clamp(finite_or(volume, 0), 0, 1), memory_order_relaxed);
    atomic_store_explicit(&a->mode, mode >= 0 && mode <= 2 ? mode : 0, memory_order_relaxed);
}
void fold_audio_click(FoldAudio *a) { if (a) atomic_store_explicit(&a->click, true, memory_order_relaxed); }

void fold_audio_render(FoldAudio *a, float *out, size_t frames) {
    if (!out) return;
    if (!a) { memset(out, 0, frames * sizeof(float)); return; }
    double p = atomic_load_explicit(&a->target_progress, memory_order_relaxed);
    double velocity = atomic_load_explicit(&a->target_velocity, memory_order_relaxed);
    double volume = atomic_load_explicit(&a->target_volume, memory_order_relaxed);
    int mode = atomic_load_explicit(&a->mode, memory_order_relaxed);
    bool clicked = atomic_exchange_explicit(&a->click, false, memory_order_relaxed);
    if (clicked && mode != 0) a->click_age = 0;
    if (mode == 0) a->click_age = 1;
    double speed = fabs(velocity);
    double gain_target = mode == 1 && speed > 1 ? 0.19 * sqrt(clamp(speed / 100, 0, 1)) * volume : 0;
    if (gain_target == 0 && a->gain < 0.000001 && a->click_age >= 0.12) {
        a->gain = 0;
        memset(out, 0, frames * sizeof(float));
        return;
    }
    double pitch = 105 + (1 - p) * 185 + fmin(speed, 100) * 0.55 + (velocity > 0 ? 32 : 0);
    double smooth = 1 - exp(-1 / (a->sample_rate * 0.014));
    for (size_t i = 0; i < frames; i++) {
        a->gain += (gain_target - a->gain) * smooth;
        a->frequency += (pitch - a->frequency) * smooth;
        a->phase = fmod(a->phase + tau * a->frequency / a->sample_rate, tau);
        a->phase2 = fmod(a->phase2 + tau * 6.5 / a->sample_rate, tau);
        double elastic = sin(a->phase + 0.85 * sin(a->phase * 2 + a->phase2));
        double sample = a->gain * (0.78 * elastic + 0.22 * sin(a->phase * 3)) * (0.88 + 0.12 * sin(a->phase2));
        if (a->click_age < 0.12 && mode != 0) {
            a->random ^= a->random << 13; a->random ^= a->random >> 17; a->random ^= a->random << 5;
            double noise = (double)a->random / UINT32_MAX * 2 - 1;
            double t = a->click_age;
            double attack = fmin(1, t * 1800);
            sample += volume * 0.24 * attack * exp(-t * 85) * (0.8 * sin(tau * 1250 * t) + 0.2 * noise);
            a->click_age += 1 / a->sample_rate;
        }
        if (mode == 0 || volume == 0) sample = 0;
        out[i] = (float)clamp(sample, -0.65, 0.65);
    }
}
