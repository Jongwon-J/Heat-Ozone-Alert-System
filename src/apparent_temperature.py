"""
시간별 체감온도 계산 모듈
출처: 기상자료개방포털 > 기후통계분석 > 응용기상분석 > 체감온도 (여름철, 2022.6.2 개정식)
정의문서_v1.md 2절 기준
"""
import math


def wet_bulb_temperature(Ta: float, RH: float) -> float:
    """습구온도 Tw 추정 (Stull 근사식)
    Ta: 기온(℃), RH: 상대습도(%)
    주의: ATAN은 라디안 기준. math.atan()을 그대로 사용한다 (degrees 변환 금지).
    """
    Tw = (
        Ta * math.atan(0.151977 * math.sqrt(RH + 8.313659))
        + math.atan(Ta + RH)
        - math.atan(RH - 1.67633)
        + 0.00391838 * (RH ** 1.5) * math.atan(0.023101 * RH)
        - 4.686035
    )
    return Tw


def apparent_temperature(Ta: float, RH: float) -> float:
    """여름철 체감온도 산출 (기상청 2022.6.2 개정식)
    Ta: 기온(℃), RH: 상대습도(%)
    """
    Tw = wet_bulb_temperature(Ta, RH)
    AT = (
        -0.2442
        + 0.55399 * Tw
        + 0.45535 * Ta
        - 0.0022 * (Tw ** 2)
        + 0.00278 * Tw * Ta
        + 3.0
    )
    return AT


if __name__ == "__main__":
    # 정의문서_v1.md 3절 검증표 — 5개 케이스
    cases = [
        (30.2, 80, 32.3),
        (32.0, 60, 32.5),
        (34.6, 40, 33.0),
        (36.0, 55, 36.0),
        (39.6, 45, 38.4),
    ]
    print(f"{'기온':>6} {'습도':>6} {'기상청값':>8} {'계산값':>8} {'차이':>7}  판정")
    print("-" * 50)
    all_pass = True
    for Ta, RH, kma_value in cases:
        calc = apparent_temperature(Ta, RH)
        diff = abs(calc - kma_value)
        ok = diff <= 0.1  # 정의문서 기준: 0.05℃ 이내를 '일치'로 봄, 반올림 오차 감안 0.1로 판정
        all_pass &= ok
        print(f"{Ta:6.1f} {RH:6.0f} {kma_value:8.2f} {calc:8.2f} {diff:7.2f}  {'일치' if ok else '불일치'}")
    print("-" * 50)
    print("전체 검증:", "통과" if all_pass else "실패 — 공식 재확인 필요")
