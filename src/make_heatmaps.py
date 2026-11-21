"""
B5 히트맵: output/6주차_시각별_사각지대_분포.csv 만 읽는다. 재계산하지 않는다.
행=오존 임계값(5종), 열=라벨 9~21시. 두 그림: (a) 사각지대 시간(D), (b) 오존 임계값 이상 시간(O).
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = os.path.join(os.path.dirname(__file__), "..", "output")
hm = pd.read_csv(os.path.join(OUT, "6주차_시각별_사각지대_분포.csv"), encoding="utf-8-sig")

LABELS = list(range(9, 22))
THS = sorted(hm["임계값_ppm"].unique())
XTICK = [f"{h}\n({h-1:02d}~{h:02d}시)" for h in LABELS]  # 라벨 HH = 실제 (HH-1)시~HH시


def draw(value_col, title, out_name, cbar_label):
    mat = hm.pivot(index="임계값_ppm", columns="라벨시각", values=value_col).reindex(index=THS, columns=LABELS)

    fig, ax = plt.subplots(figsize=(13, 5.5))
    im = ax.imshow(mat.values, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(LABELS)))
    ax.set_xticklabels(XTICK, fontsize=9)
    ax.set_yticks(range(len(THS)))
    ax.set_yticklabels([f"{t:.2f}" for t in THS])
    ax.set_xlabel("라벨 시각 HH  (= 실제 (HH-1)시~HH시, 근무시간대 라벨 11~18 강조)")
    ax.set_ylabel("오존 임계값 (ppm)")
    ax.set_title(f"{title}\n(라벨 11~18, 방식3 측정소 중앙값, 2018~2025 연평균)")

    vmax = mat.values.max()
    for i in range(len(THS)):
        for j in range(len(LABELS)):
            v = mat.values[i, j]
            color = "white" if v > vmax * 0.6 else "black"
            ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=8, color=color)

    # 근무시간대(라벨 11~18) 영역 테두리로 강조
    work_idx = [LABELS.index(h) for h in range(11, 19)]
    ax.axvspan(work_idx[0] - 0.5, work_idx[-1] + 0.5, fill=False, edgecolor="blue", linewidth=1.5, linestyle="--")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(cbar_label)
    fig.tight_layout()
    out_path = os.path.join(OUT, out_name)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"저장: {out_path}")
    return out_path


p1 = draw("합계_연평균시간", "시각 × 오존 임계값별 사각지대 시간(D=Type A+B, 연평균 h)",
          "6주차_시각별_히트맵_사각지대시간.png", "연평균 시간(h)")
p2 = draw("오존초과_연평균시간(특보무관)", "시각 × 오존 임계값별 오존 임계값 이상 시간(특보 무관, 연평균 h)",
          "6주차_시각별_히트맵_오존임계값이상시간.png", "연평균 시간(h)")
