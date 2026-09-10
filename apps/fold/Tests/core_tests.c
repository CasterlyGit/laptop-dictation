#include "FoldCore.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static void report_tests(void) {
    double a = -1;
    const uint8_t open[] = {1, 120, 0}, closed[] = {1, 0, 0};
    const uint8_t wrong[] = {2, 120, 0}, bad[] = {1, 255, 255}, two[] = {1, 100};
    assert(fold_decode_report(open, sizeof(open), &a) && a == 120);
    assert(fold_decode_report(closed, sizeof(closed), &a) && a == 0);
    assert(!fold_decode_report(NULL, 8, &a));
    assert(!fold_decode_report(two, sizeof(two), &a));
    assert(!fold_decode_report(wrong, sizeof(wrong), &a));
    assert(!fold_decode_report(bad, sizeof(bad), &a));
    assert(fold_progress(150, 105) == 0 && fold_progress(0, 105) == 1);
    assert(fold_progress(NAN, 105) == 0);
    double last = 1;
    for (int i = 0; i <= 180; i++) {
        double p = fold_progress(i, 105);
        assert(isfinite(p) && p >= 0 && p <= last); last = p;
    }
    puts("PASS: report validation, units, invalid inputs, monotonic progress");
}

static void motion_tests(void) {
    FoldMotion m; fold_motion_reset(&m);
    double t = 0; FoldReading r = fold_motion_update(&m, 120, t, 105);
    assert(r.velocity == 0 && !r.opened && r.progress == 0);
    int clicks = 0;
    for (int raw = 120; raw >= 25; raw--) { t += 1.0/30; r = fold_motion_update(&m, raw, t, 105); clicks += r.opened; }
    assert(r.velocity < 0 && clicks == 0 && r.progress > 0.9);
    for (int i = 0; i < 30; i++) { t += 1.0/30; r = fold_motion_update(&m, 25, t, 105); }
    assert(r.velocity == 0);
    for (int raw = 25; raw <= 120; raw++) { t += 1.0/30; r = fold_motion_update(&m, raw, t, 105); clicks += r.opened; }
    assert(r.velocity > 0 && clicks == 1);
    for (int i = 0; i < 60; i++) { t += 1.0/30; r = fold_motion_update(&m, 120, t, 105); clicks += r.opened; }
    assert(clicks == 1 && r.velocity == 0);
    r = fold_motion_update(&m, 20, t + 3, 105);
    assert(r.velocity == 0 && !r.opened);
    r = fold_motion_update(&m, 120, t + 6, 105);
    assert(!r.opened); // Wake at a different angle must not replay a stale click.
    puts("PASS: close/open direction, stationary decay, one click, wake reset");
}

static void mesh_tests(void) {
    size_t n = fold_mesh_count(8, 56);
    FoldVertex *v = calloc(n, sizeof(*v)); assert(v);
    assert(!fold_make_mesh(v, n - 1, 8, 56, 0, 1));
    assert(!fold_mesh_count(-1, 56) && !fold_mesh_count(100000, 100000));
    for (int step = 0; step <= 100; step++) {
        float p = step / 100.0f;
        assert(fold_make_mesh(v, n, 8, 56, p, 1) == n);
        for (size_t i = 0; i < n; i++) {
            assert(isfinite(v[i].x) && isfinite(v[i].y));
            assert(v[i].x >= -1.0001 && v[i].x <= 1.0001 && v[i].y >= -1.0001 && v[i].y <= 1.0001);
            if (v[i].v == 1) { assert(fabs(v[i].y + 1) < 1e-5); assert(fabs(v[i].x - (2*v[i].u-1)) < 1e-5); }
            if (step == 0) { assert(fabs(v[i].x-(2*v[i].u-1)) < 1e-5); assert(fabs(v[i].y-(1-2*v[i].v)) < 1e-5); }
        }
        for (size_t i = 0; i < n; i += 3) {
            float area = (v[i+1].x-v[i].x)*(v[i+2].y-v[i].y)-(v[i+1].y-v[i].y)*(v[i+2].x-v[i].x);
            assert(area > 0); // No inverted or degenerate triangles at any fold amount.
        }
    }
    free(v);
    puts("PASS: full mesh sweep, identity, fixed hinge, bounded geometry, triangle winding");
}

static void audio_tests(void) {
    assert(!fold_audio_create(0) && !fold_audio_create(NAN));
    for (int rateIndex = 0; rateIndex < 3; rateIndex++) {
        int rate = (int[]){44100, 48000, 96000}[rateIndex];
        FoldAudio *a = fold_audio_create(rate); assert(a);
        float samples[512];
        fold_audio_set(a, 0.6, 0, 1, 1);
        fold_audio_render(a, samples, 512);
        for (int i = 0; i < 512; i++) assert(samples[i] == 0);
        fold_audio_set(a, 0.6, -60, 1, 1);
        double energy = 0;
        for (int b = 0; b < 20; b++) {
            fold_audio_render(a, samples, 512);
            for (int i = 0; i < 512; i++) { assert(isfinite(samples[i]) && fabs(samples[i]) <= 0.65); energy += samples[i]*samples[i]; }
        }
        assert(energy > 0.1);
        fold_audio_set(a, 0.6, 0, 1, 1);
        for (int b = 0; b < 100; b++) fold_audio_render(a, samples, 512);
        for (int i = 0; i < 512; i++) assert(fabs(samples[i]) < 0.00001);
        fold_audio_set(a, 0, 0, 0.8, 2); fold_audio_click(a); energy = 0;
        fold_audio_render(a, samples, 512);
        for (int i = 0; i < 512; i++) energy += samples[i]*samples[i];
        assert(energy > 0);
        fold_audio_set(a, 0, 100, 1, 0); fold_audio_render(a, samples, 512);
        for (int i = 0; i < 512; i++) assert(samples[i] == 0); // Emergency silence is immediate.
        fold_audio_set(a, NAN, INFINITY, NAN, 99); fold_audio_render(a, samples, 512);
        for (int i = 0; i < 512; i++) assert(samples[i] == 0);
        fold_audio_destroy(a);
    }
    puts("PASS: three audio rates, stationary silence, audible motion/click, peak bound, instant mute");
}

int main(void) { report_tests(); motion_tests(); mesh_tests(); audio_tests(); puts("All core checks passed."); return 0; }
