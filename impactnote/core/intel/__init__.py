"""Evidence-driven project intelligence engine.

프로젝트 경로 하나로 문서·코드·Git 이력을 수집하고, 문서와 구현을 교차 분석해
근거가 연결된 성과 후보를 만든다. Git 커밋 메시지는 단서일 뿐이며,
최종 후보는 코드/문서/측정 근거와 신뢰도 등급을 함께 가진다.
"""

from impactnote.core.intel.engine import analyze_project
from impactnote.core.intel.models import (
    QUALITY_LEVELS,
    Candidate,
    CodeFile,
    DocRecord,
    EvidenceRef,
    GitCommit,
    ProjectAnalysis,
)

__all__ = [
    "QUALITY_LEVELS",
    "Candidate",
    "CodeFile",
    "DocRecord",
    "EvidenceRef",
    "GitCommit",
    "ProjectAnalysis",
    "analyze_project",
]
