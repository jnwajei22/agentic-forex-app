from app.services.technical_analysis.fibonacci import calculate_fib_levels

def test_long_fib_levels():
    levels = calculate_fib_levels(1.0, 2.0, "long")
    assert round(levels["0.500"], 3) == 1.5
    assert round(levels["0.618"], 3) == 1.382

def test_short_fib_levels():
    levels = calculate_fib_levels(1.0, 2.0, "short")
    assert round(levels["0.500"], 3) == 1.5
    assert round(levels["0.618"], 3) == 1.618
