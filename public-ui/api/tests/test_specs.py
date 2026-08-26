"""The spec parser is the load-bearing part of alert criteria — the pipeline
stores no structured numbers, so everything numeric a user can filter on
comes from here."""
from core import specs


def test_pulls_the_common_subto_numbers():
    post = ("Atlanta GA. Loan balance is $185,000 at 4.25%, monthly payment of "
            "$1,450/mo. Tenant occupied. Asking 195k, ARV around 260k. 30 year term.")
    out = specs.extract(post, {}, ["Atlanta"])
    assert out["loan_balance"]["value"] == 185_000
    assert out["interest_rate"]["value"] == 4.25
    assert out["monthly_payment"]["value"] == 1_450
    assert out["asking_price"]["value"] == 195_000
    assert out["ARV"]["value"] == 260_000
    assert out["term"]["value"] == 360           # normalized to months
    assert out["occupancy_status"]["value"] == "tenant occupied"


def test_stored_values_win_over_parsed_ones():
    """The day the pipeline starts persisting specs, they take precedence
    with no change here."""
    out = specs.extract("asking 195k", {"asking_price": 201_000}, [])
    assert out["asking_price"] == {"value": 201_000, "source": "stored", "snippet": ""}


def test_absent_fields_are_absent_never_guessed():
    out = specs.extract("Nice house, DM me", {}, [])
    assert "loan_balance" not in out
    assert "interest_rate" not in out


def test_shorthand_and_bare_thousands():
    assert specs.extract("asking 1.2M", {}, [])["asking_price"]["value"] == 1_200_000
    # "asking 195" in a real estate post means 195k, not $195
    assert specs.extract("asking 195", {}, [])["asking_price"]["value"] == 195_000


def test_implausible_rate_is_rejected():
    out = specs.extract("90% of sellers say yes", {}, [])
    assert "interest_rate" not in out


def test_location_comes_from_the_pipelines_own_city_detection():
    out = specs.extract("great deal", {}, ["Atlanta", "Savannah"])
    assert out["location"]["value"] == "Atlanta, Savannah"
    assert "location" not in specs.extract("great deal", {}, [])
