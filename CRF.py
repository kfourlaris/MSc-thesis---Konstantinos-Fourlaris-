def calculate_annuity_factor(interest_rate, lifespan):
    """
    Calculates the Capital Recovery Factor (CRF).
    """
    if interest_rate == 0:
        return 1 / lifespan
    return (interest_rate * (1 + interest_rate)**lifespan) / ((1 + interest_rate)**lifespan - 1)

# For your case
i = 0.12
n = 20
annuity_factor = calculate_annuity_factor(i, n)
