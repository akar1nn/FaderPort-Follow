"""Reproduce the panel regression and optional Matplotlib figure offline.

No fitting or plotting dependencies are used by the installed control surface.
Run with --plot after installing Matplotlib for development only.
"""

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from FaderPort_Follow.monotone import MonotoneSpline


def least_squares(samples):
    """Equal-weight affine regression of raw MIDI against measured millimeters."""
    mean_x = sum(x for x, _ in samples) / len(samples)
    mean_y = sum(y for _, y in samples) / len(samples)
    scale = sum((x - mean_x) * (y - mean_y) for x, y in samples) / sum(
        (x - mean_x) ** 2 for x, _ in samples)
    offset = mean_y - scale * mean_x
    return offset, scale


def fit(observations_path):
    observations = json.loads(Path(observations_path).read_text(encoding="utf-8"))
    distances = {"-inf": 0.0}
    for item in reversed(observations["ruler_measurements_mm"]):
        distances[item["from_db"]] = distances[item["to_db"]] + item["distance_mm"]
    rows = observations["measurements"]
    samples = [(distances[row["panel_db"]], row["raw_14bit"]) for row in rows]
    offset, scale = least_squares(samples)
    residuals = [y - offset - scale * x for x, y in samples]
    mean_y = sum(y for _, y in samples) / len(samples)
    # +/-1 ruler estimates are dependent geometry, not independent fit samples.
    distances[-1] = distances[0] - 4.0
    distances[1] = distances[0] + 4.0
    panel = [(db, (offset + scale * mm) / 16383.0)
             for db, mm in sorted((db, mm) for db, mm in distances.items() if db != "-inf")]
    spline = MonotoneSpline(panel)
    report = {
        "model": "raw = offset + scale * cumulative_panel_mm; monotone cubic Hermite dB-to-travel",
        "fit_samples": 10,
        "weights": "Equal: ruler and manual placement precision are unknown; no inferred inverse-variance weighting",
        "offset_raw": offset,
        "scale_raw_per_mm": scale,
        "rmse_raw": math.sqrt(sum(r * r for r in residuals) / len(samples)),
        "rmse_mm": math.sqrt(sum(r * r for r in residuals) / len(samples)) / scale,
        "r_squared": 1 - sum(r * r for r in residuals) / sum((y - mean_y) ** 2 for _, y in samples),
        "maximum_absolute_residual_mm": max(abs(r) for r in residuals) / scale,
        "ceiling_db": 6,
        "ceiling_raw": spline(6) * 16383,
        "knots": [{"db": db, "cumulative_mm": distances[db], "physical_normalized": position}
                  for db, position in panel],
        "residuals": [{"panel_db": row["panel_db"], "observed_raw": row["raw_14bit"],
                       "residual_raw": residual, "residual_mm": residual / scale}
                      for row, residual in zip(rows, residuals)],
        "limits": ["Fit residuals measure consistency of existing data, not independent hardware accuracy",
                   "Ruler estimates are approximate; +1/-1 are geometry-derived, not independent MIDI observations",
                   "No compensation for direction-dependent motor backlash or friction",
                   "Below -60 dB, a monotone power tail joins Live native silence; no fixed dB silence threshold",
                   "At +6, clamping intentionally introduces a slope break and a many-to-one overtravel region"],
    }
    destination = ROOT / "FaderPort_Follow/calibration_profile.py"
    source = ['"""Default panel calibration profile. See docs/CURVE_FIT.md."""', "",
              "# Raw MIDI = %.12f + %.12f * cumulative panel millimeters." % (offset, scale),
              "# Nine fitted marks plus two ruler-derived +/-1 marks.",
              "FITTED_MARKS = ("]
    source.extend("    (%.15f, %g)," % (position, db) for db, position in panel if db < 6)
    source.extend([")", "FITTED_UPPER_MARK = (%.15f, 10)" % panel[-1][1], ""])
    destination.write_text("\n".join(source), encoding="utf-8")
    report_dir = ROOT / "tmp"
    report_dir.mkdir(exist_ok=True)
    (report_dir / "curve-fit-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report, spline, rows


def plot(report, spline, rows):
    local_plot_deps = ROOT / "tmp/plot-deps"
    if local_plot_deps.exists():
        sys.path.insert(0, str(local_plot_deps))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["svg.fonttype"] = "path"
    fig = plt.figure(figsize=(12.4, 8.3), facecolor="#f6f8fb", layout="constrained")
    grid = fig.add_gridspec(2, 2, height_ratios=(2.2, 1))
    main = fig.add_subplot(grid[0, 0])
    detail = fig.add_subplot(grid[0, 1])
    residual = fig.add_subplot(grid[1, :])
    for ax in (main, detail, residual):
        ax.set_facecolor("white")
        ax.grid(True, color="#dfe5ee", alpha=0.65, linewidth=0.7)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=9)
    dbs = [-60 + i * 70 / 1600 for i in range(1601)]
    positions = [100 * spline(db) for db in dbs]
    raw_positions = [row["physical_normalized"] * 100 for row in rows]
    raw_dbs = [row["panel_db"] for row in rows]
    ceiling = spline(6) * 100
    for ax in (main, detail):
        ax.plot(positions, dbs, color="#a9b4c4", linestyle="--", linewidth=1.3,
                label="Fitted panel scale (including +10 reference)")
        active = [(x, db) for x, db in zip(positions, dbs) if db <= 6]
        ax.plot([p[0] for p in active] + [ceiling, 100],
                [p[1] for p in active] + [6, 6], color="#2364d2", linewidth=2.4,
                label="Target volume (+6 dB clamp)")
        ax.scatter(raw_positions, raw_dbs, s=28, facecolor="white", edgecolor="#e88428",
                   linewidth=1.4, zorder=5, label="Raw manual MIDI samples")
        ax.scatter([spline(-1) * 100, spline(1) * 100], [-1, 1], marker="x", s=40,
                   color="#7a4aa8", zorder=6, label="Ruler-derived +/-1 dB")
        ax.axvspan(ceiling, 100, color="#2364d2", alpha=0.055)
        ax.set_xlabel("Physical fader position / full travel %", fontsize=10)
        ax.set_ylabel("Target volume / dB", fontsize=10)
    main.set(xlim=(0, 100), ylim=(-64, 12), title="Overall curve: segmented, smooth, and monotone")
    main.set_yticks([-60, -50, -40, -30, -20, -10, 0, 6, 10])
    main.legend(loc="upper left", fontsize=8, frameon=False)
    main.annotate("Below -60: smooth tail to Live native minimum\nNo independent dB samples", xy=(3, -61),
                  xytext=(20, -55), fontsize=8, color="#637187",
                  arrowprops={"arrowstyle": "-", "color": "#a9b4c4"})
    detail.set(xlim=(54, 100), ylim=(-6, 11), title="Zero and upper range: +/-1 extension, +6 return")
    detail.set_yticks([-5, -1, 0, 1, 5, 6, 10])
    detail.annotate("Release returns to +6\nAbout %.2f%% travel" % ceiling, xy=(ceiling, 6), xytext=(66, 8),
                    fontsize=9, arrowprops={"arrowstyle": "->", "color": "#2364d2"})
    errors = [row["residual_mm"] for row in report["residuals"]]
    residual.bar(range(len(rows)), errors, color=["#2364d2" if y >= 0 else "#e88428" for y in errors], width=.55)
    residual.axhline(0, color="#637187", linewidth=.8)
    residual.set_xticks(range(len(rows)), ["%+g" % row["panel_db"] for row in rows])
    residual.set(xlabel="Sampled panel mark / dB", ylabel="Position residual / mm",
                 title="Regression residual: observed minus fitted position", ylim=(-.4, .4))
    fig.suptitle("FaderPort Follow - Regression calibration curve", fontsize=19, fontweight="bold", x=.03, ha="left")
    fig.supxlabel("Ten-point equal-weight least squares - RMS %.3f mm - R2 %.6f\n"
                  "Fit error describes sample consistency, not motor accuracy; Live parameter conversion is sampled separately and read-only."
                  % (report["rmse_mm"], report["r_squared"]), fontsize=9, color="#55647a")
    output = ROOT / "docs/figures"
    output.mkdir(exist_ok=True)
    fig.savefig(output / "faderport-regression.png", dpi=180)
    fig.savefig(output / "faderport-regression.svg")
    plt.close(fig)
    print(output / "faderport-regression.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="Path to your panel measurements JSON")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    result, curve, measurements = fit(args.input)
    print(json.dumps({key: result[key] for key in ("offset_raw", "scale_raw_per_mm", "rmse_mm", "r_squared", "ceiling_raw")}, indent=2))
    if args.plot:
        plot(result, curve, measurements)
