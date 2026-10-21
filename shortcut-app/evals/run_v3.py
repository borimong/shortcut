"""Run adjusted scenarios against the isolated V3 app. Existing metric/pass logic is unchanged."""
import os
import sys
os.environ.setdefault("SHORTCUT_URL", "http://localhost:18880")
from . import run_eval
from .v3_scenarios import scenarios


def main():
    run_eval.SCENARIOS=scenarios(run_eval.Scenario,run_eval.Step)
    if any(flag in sys.argv for flag in ("--help", "-h", "--compare")):
        return run_eval.main()
    api=run_eval.Api()
    try:
        info=api.call("GET", "/internal/test/v3/info")
        if info.get("dataset")!="V3" or info.get("scenes")!=24:
            raise RuntimeError("V3 앱/24씬 연결을 먼저 확인하세요.")
    finally:
        api.http.close()
    run_eval.main()

if __name__=="__main__":
    main()
