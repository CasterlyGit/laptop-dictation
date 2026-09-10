#ifndef FOLD_CORE_H
#define FOLD_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// All angles are whole degrees from the HID feature report, NOT centidegrees.
bool fold_decode_report(const uint8_t *bytes, size_t length, double *angle);
double fold_progress(double angle, double clear_angle);

typedef struct {
    double angle, velocity, last_raw, last_time, still_time;
    bool initialized, was_folded;
} FoldMotion;
typedef struct { double angle, velocity, progress; bool opened; } FoldReading;
void fold_motion_reset(FoldMotion *motion);
FoldReading fold_motion_update(FoldMotion *motion, double raw, double time, double clear_angle);

// Texture coordinates have their origin at the top left. Positions are Metal clip coordinates.
typedef struct { float x, y, u, v; } FoldVertex;
size_t fold_mesh_count(int columns, int rows);
size_t fold_make_mesh(FoldVertex *vertices, size_t capacity, int columns, int rows,
                      float progress, float perspective);

typedef struct FoldAudio FoldAudio;
// 0 = silent, 1 = elastic movement, 2 = open click. Only the render thread owns DSP state.
FoldAudio *fold_audio_create(double sample_rate);
void fold_audio_destroy(FoldAudio *audio);
void fold_audio_set(FoldAudio *audio, double progress, double velocity, double volume, int mode);
void fold_audio_click(FoldAudio *audio);
void fold_audio_render(FoldAudio *audio, float *output, size_t frames);
#endif
