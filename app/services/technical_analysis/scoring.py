def score_setup(
    trend_alignment: int,
    fib_quality: int,
    sr_confluence: int,
    candle_confirmation: int,
    reward_risk: int,
    spread_session: int,
    news_safety: int,
) -> int:
    score = sum([
        trend_alignment,
        fib_quality,
        sr_confluence,
        candle_confirmation,
        reward_risk,
        spread_session,
        news_safety,
    ])
    return max(0, min(100, score))

def label_score(score: int) -> str:
    if score >= 80:
        return "strong"
    if score >= 65:
        return "watch"
    if score >= 50:
        return "weak"
    return "no_setup"
