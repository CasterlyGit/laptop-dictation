#include <metal_stdlib>
using namespace metal;
struct Vertex { float x, y, u, v; };
struct Raster { float4 position [[position]]; float2 uv; };
struct Appearance { float progress, blur, shadow, padding; };
vertex Raster fold_vertex(const device Vertex *vertices [[buffer(0)]], uint i [[vertex_id]]) {
    Vertex v = vertices[i];
    return { float4(v.x, v.y, 0, 1), float2(v.u, v.v) };
}
fragment float4 fold_fragment(Raster in [[stage_in]], texture2d<float> desktop [[texture(0)]],
                             constant Appearance &look [[buffer(0)]]) {
    constexpr sampler s(coord::normalized, address::clamp_to_edge, filter::linear);
    float2 uv = in.uv;
    float top = 1 - uv.y;
    float radius = look.progress * look.blur * top * top * 18;
    float2 step = radius / float2(desktop.get_width(), desktop.get_height());
    float3 color = desktop.sample(s, uv).rgb * 0.24;
    color += desktop.sample(s, uv + float2(step.x, 0)).rgb * 0.12;
    color += desktop.sample(s, uv - float2(step.x, 0)).rgb * 0.12;
    color += desktop.sample(s, uv + float2(0, step.y)).rgb * 0.12;
    color += desktop.sample(s, uv - float2(0, step.y)).rgb * 0.12;
    color += desktop.sample(s, uv + step).rgb * 0.07;
    color += desktop.sample(s, uv - step).rgb * 0.07;
    color += desktop.sample(s, uv + float2(step.x, -step.y)).rgb * 0.07;
    color += desktop.sample(s, uv + float2(-step.x, step.y)).rgb * 0.07;
    float edge = pow(abs(uv.x - 0.5) * 2, 3);
    float shade = look.progress * look.shadow * (0.34 * top + 0.28 * edge * top * top);
    return float4(color * (1 - shade), 1);
}
