import math

from app import verify as verifier
from app.constants import Scenario, Verdict
from app.simulate import simulate


def test_schedule_is_deterministic_and_distinct():
    a = verifier.generate_schedule("seed-x", 100, 20)
    b = verifier.generate_schedule("seed-x", 100, 20)
    assert a == b
    assert len(a) == 20 == len(set(a))
    assert all(0 <= i < 100 for i in a)


def test_p_evade_math():
    assert verifier.p_evade(0.0, 20) == 0.0
    assert math.isclose(verifier.p_evade(0.5, 20), math.exp(-10), rel_tol=1e-9)
    assert verifier.p_evade(0.7, 20) < 1e-5  # gross fakery almost surely caught


def test_legitimate_job_verifies():
    tele = simulate("job-legit", 120, Scenario.LEGITIMATE)
    commits = verifier.commit_all("job-legit", tele)
    res = verifier.verify_job("job-legit", tele, commits, n=20)
    assert res["verdict"] == Verdict.VERIFIED_A0
    assert res["sampling_ok"] is True
    assert res["screening_failures"] == 0


def test_lazy_fake_is_caught_by_sampling():
    tele = simulate("job-fake", 120, Scenario.LAZY_FAKE)
    commits = verifier.commit_all("job-fake", tele)
    res = verifier.verify_job("job-fake", tele, commits, n=20)
    assert res["verdict"] == Verdict.FAILED
    assert res["p_evade"] < 1e-3


def test_localized_sabotage_is_caught_and_fails_closed():
    # Sampling may miss a localized defect, but continuous screening catches it
    # AND gates the verdict, so a sabotaged part can never show Verified@A0.
    tele = simulate("job-sab", 200, Scenario.SABOTAGED)
    commits = verifier.commit_all("job-sab", tele)
    res = verifier.verify_job("job-sab", tele, commits, n=20)
    assert res["screening_failures"] > 0  # screening detects the void
    assert res["faked_fraction"] > 0
    assert res["verdict"] == Verdict.FAILED  # fail-closed: never Verified@A0
    assert res["screening_ok"] is False


def test_replay_of_another_jobs_commitments_rejected():
    # commitments are bound to the job id; replaying job A's telemetry and
    # commitments under a new job id fails the per-bucket integrity recompute.
    tele = simulate("job-A", 120, Scenario.LEGITIMATE)
    commits_a = verifier.commit_all("job-A", tele)
    res = verifier.verify_job("job-B", tele, commits_a, n=20)
    assert res["verdict"] == Verdict.FAILED
    assert len(res["sampled_failures"]) > 0
    assert all(f["integrity"] is False for f in res["sampled_failures"])


def test_legitimate_never_false_fails():
    # legitimate readings are clipped into envelope, so screening is clean
    for i in range(5):
        tele = simulate(f"job-leg-{i}", 150, Scenario.LEGITIMATE)
        commits = verifier.commit_all(f"job-leg-{i}", tele)
        res = verifier.verify_job(f"job-leg-{i}", tele, commits, n=20)
        assert res["verdict"] == Verdict.VERIFIED_A0
        assert res["screening_failures"] == 0
