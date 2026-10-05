// SPDX-FileCopyrightText: 2026 Lampway contributors
//
// SPDX-License-Identifier: GPL-3.0-or-later
//
// lampway-quadremesh: OBJ in, all-quad OBJ out, through the MIT-licensed AutoRemesher core. No Qt, no window, no GL, no network.
// Arguments mirror the AutoRemesher application's headless mode (--input --output --report --target-quads --edge-scaling --sharp-edge
// --smooth-normal --adaptivity --anisotropy) plus --hard-surface. Exit code 0 only when a mesh was written.
#include <AutoRemesher/AutoRemesher>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Params {
    std::string input, output, report;
    long targetQuads = 50000;
    double edgeScaling = 1.0, sharpEdge = 90.0, smoothNormal = 0.0, adaptivity = 1.0, anisotropy = 1.0;
    bool hardSurface = false;
};

bool readObj(const std::string& path, std::vector<AutoRemesher::Vector3>& vertices, std::vector<std::vector<size_t>>& triangles, std::string& error)
{
    std::ifstream in(path);
    if (!in) {
        error = "cannot open " + path;
        return false;
    }
    std::string line;
    while (std::getline(in, line)) {
        std::istringstream ss(line);
        std::string tag;
        ss >> tag;
        if (tag == "v") {
            double x, y, z;
            if (!(ss >> x >> y >> z)) {
                error = "bad vertex line: " + line;
                return false;
            }
            vertices.emplace_back(x, y, z);
        } else if (tag == "f") {
            std::vector<long> idx;
            std::string tok;
            while (ss >> tok) {
                long i = std::strtol(tok.c_str(), nullptr, 10);
                if (i < 0)
                    i = (long)vertices.size() + i + 1;
                if (i < 1 || (size_t)i > vertices.size()) {
                    error = "face index out of range: " + line;
                    return false;
                }
                idx.push_back(i - 1);
            }
            for (size_t k = 2; k < idx.size(); ++k)
                triangles.push_back({ (size_t)idx[0], (size_t)idx[k - 1], (size_t)idx[k] });
        }
    }
    if (vertices.empty() || triangles.empty()) {
        error = "the input has no triangles";
        return false;
    }
    return true;
}

void progress(void*, float p, const char* status)
{
    std::fprintf(stdout, "%d%% done. %s\n", (int)(p * 100), status ? status : "");
    std::fflush(stdout);
}

bool inRange(const char* name, double v, double lo, double hi)
{
    if (v < lo || v > hi) {
        std::fprintf(stderr, "error: %s must be between %g and %g\n", name, lo, hi);
        return false;
    }
    return true;
}

}

int main(int argc, char** argv)
{
    Params p;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&](const char* n) -> const char* {
            if (i + 1 >= argc) {
                std::fprintf(stderr, "error: %s needs a value\n", n);
                std::exit(2);
            }
            return argv[++i];
        };
        if (a == "--input" || a == "-i") p.input = next("--input");
        else if (a == "--output" || a == "-o") p.output = next("--output");
        else if (a == "--report") p.report = next("--report");
        else if (a == "--target-quads") p.targetQuads = std::strtol(next(a.c_str()), nullptr, 10);
        else if (a == "--edge-scaling") p.edgeScaling = std::atof(next(a.c_str()));
        else if (a == "--sharp-edge") p.sharpEdge = std::atof(next(a.c_str()));
        else if (a == "--smooth-normal") p.smoothNormal = std::atof(next(a.c_str()));
        else if (a == "--adaptivity") p.adaptivity = std::atof(next(a.c_str()));
        else if (a == "--anisotropy") p.anisotropy = std::atof(next(a.c_str()));
        else if (a == "--hard-surface") p.hardSurface = true;
        else if (a == "--version") { std::puts("lampway-quadremesh (AutoRemesher core 1.2.0, MIT)"); return 0; }
        else { std::fprintf(stderr, "error: unknown argument %s\n", a.c_str()); return 2; }
    }
    if (p.input.empty() || p.output.empty()) {
        std::fprintf(stderr, "usage: lampway-quadremesh --input in.obj --output out.obj [--report r.txt] [--target-quads N] [--edge-scaling 1..4] [--sharp-edge 30..180] [--smooth-normal 0..180] [--adaptivity 0..1] [--anisotropy 0..1] [--hard-surface]\n");
        return 2;
    }
    if (p.targetQuads < 25 || !inRange("--edge-scaling", p.edgeScaling, 1, 4) || !inRange("--sharp-edge", p.sharpEdge, 30, 180) || !inRange("--smooth-normal", p.smoothNormal, 0, 180)
        || !inRange("--adaptivity", p.adaptivity, 0, 1) || !inRange("--anisotropy", p.anisotropy, 0, 1)) {
        std::fprintf(stderr, "error: --target-quads must be at least 25\n");
        return 2;
    }
    std::vector<AutoRemesher::Vector3> vertices;
    std::vector<std::vector<size_t>> triangles;
    std::string error;
    if (!readObj(p.input, vertices, triangles, error)) {
        std::fprintf(stderr, "error: %s\n", error.c_str());
        return 3;
    }
    auto t0 = std::chrono::steady_clock::now();
    AutoRemesher::AutoRemesher remesher(vertices, triangles);
    remesher.setScaling(p.edgeScaling);
    remesher.setTargetTriangleCount((size_t)p.targetQuads * 2);
    remesher.setModelType(p.hardSurface ? AutoRemesher::ModelType::HardSurface : AutoRemesher::ModelType::Organic);
    remesher.setGradientAdaptivity(p.adaptivity);
    remesher.setAnisotropy(p.anisotropy);
    remesher.setSharpEdgeDegrees(p.sharpEdge);
    remesher.setSmoothNormalDegrees(p.smoothNormal);
    remesher.setProgressHandler(progress);
    if (!remesher.remesh()) {
        std::fprintf(stderr, "error: the remesher produced no mesh\n");
        return 4;
    }
    const auto& rv = remesher.remeshedVertices();
    const auto& rq = remesher.remeshedQuads();
    size_t quads = 0, nonQuads = 0;
    std::ofstream out(p.output);
    if (!out) {
        std::fprintf(stderr, "error: cannot write %s\n", p.output.c_str());
        return 5;
    }
    for (const auto& v : rv)
        out << "v " << v.x() << " " << v.y() << " " << v.z() << "\n";
    for (const auto& f : rq) {
        (f.size() == 4 ? quads : nonQuads)++;
        out << "f";
        for (size_t i : f)
            out << " " << (i + 1);
        out << "\n";
    }
    out.close();
    double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("=== Report ===\nQuads: %zu\nNon-quads: %zu\nVertices: %zu\nTime: %g seconds\n==============\n", quads, nonQuads, rv.size(), seconds);
    if (!p.report.empty()) {
        std::ofstream r(p.report);
        r << "Quads: " << quads << "\nNon-quads: " << nonQuads << "\nVertices: " << rv.size() << "\nTime: " << seconds << " seconds\n";
    }
    return 0;
}
