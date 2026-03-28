from engine import MahjongEngine, ReactionClaim


def test_priority_hu_beats_pon_and_chi():
    eng = MahjongEngine()
    claims = [
        ReactionClaim(seat=1, action="pon", candidate=10),
        ReactionClaim(seat=2, action="chi_l", candidate=(1, 2, 3)),
        ReactionClaim(seat=3, action="hu", candidate=10),
    ]
    winner = eng.resolve_reaction_priority(claims, discarder=0)
    assert winner is not None
    assert winner.action == "hu"
    assert winner.seat == 3


def test_same_priority_uses_clockwise_order():
    eng = MahjongEngine()
    # Same priority (pon), discarder=0 -> clockwise order is 1,2,3,0.
    claims = [
        ReactionClaim(seat=2, action="pon", candidate=11),
        ReactionClaim(seat=1, action="pon", candidate=11),
        ReactionClaim(seat=3, action="pon", candidate=11),
    ]
    winner = eng.resolve_reaction_priority(claims, discarder=0)
    assert winner is not None
    assert winner.seat == 1


def test_multi_hu_uses_clockwise_order():
    eng = MahjongEngine()
    # discarder=2 -> clockwise order: 3,0,1,2
    claims = [
        ReactionClaim(seat=0, action="hu", candidate=11),
        ReactionClaim(seat=3, action="hu", candidate=11),
        ReactionClaim(seat=1, action="hu", candidate=11),
    ]
    winner = eng.resolve_reaction_priority(claims, discarder=2)
    assert winner is not None
    assert winner.action == "hu"
    assert winner.seat == 3
