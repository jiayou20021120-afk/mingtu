"""命途 mingtu — 八字与紫微斗数双轴人生全流程推演。

Four layers, and only the last one is allowed to improvise:
  L0 calendar   chart.build()      lunar-python + iztro-py
  L1 rules      chart.build()      旺衰 / 用神 / 格局 / 关系 / 神煞
  L2 timeline   lifeline.build()   六维逐年打分，两套体系交叉对账
  L3 narrative  — left to the reader (human or LLM), see skill/references/
"""
__version__ = "0.1.0"

from .chart import build as build_chart          # noqa: F401
from .lifeline import build as build_lifeline    # noqa: F401
from .yunshi import build as build_yunshi        # noqa: F401
from .render import build_html                   # noqa: F401
