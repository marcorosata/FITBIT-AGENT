"""Affect inference — probabilistic emotional state estimation from Fitbit data.

This package implements evidence-based inference of affective dimensions
(arousal, stress, valence) and optional discrete emotion classification
from physiological signals available through the Fitbit Web API.

Architecture
------------
1. **Feature engineering** (`features.py`)
   - Windowed aggregation of sensor time-series
   - Personalised baselines via EWMA
   - Activity-context classification (rest vs. movement)
   - Quality gating (sync lag, wear detection, data sufficiency)

2. **Inference engine** (`inference.py`)
   - Arousal scoring (HR deviation at rest + HRV/BR/temp trends)
   - Stress scoring (sustained HR ↑ + HRV ↓ + sleep fragmentation)
   - Valence estimation (low-confidence proxy from sleep quality / HRV)
   - Discrete emotions mapped as wrappers over arousal/valence with
     explicit low-confidence flags

3. **EMA** (`ema.py`)
   - Ecological Momentary Assessment prompting and label management
   - Ground truth collection for model calibration

Confidence & limitations
------------------------
- **Arousal/stress**: Medium–High confidence when activity confounders
  are controlled.  HRV and breathing rate are sleep-only in Fitbit API.
- **Valence / discrete emotions**: Low confidence without contextual
  signals (EMA, app events).  Always presented as probabilistic
  estimates, never diagnoses.

See the project-level specification document for full scientific
rationale and Fitbit API constraints.
"""

from wearable_agent.affect.models import (
    ActivityContext,
    AffectiveState,
    ArousalLevel,
    Confidence,
    DiscreteEmotion,
    EMALabel,
    EmotionPrediction,
    FeatureWindow,
    InferenceOutput,
    QualityFlags,
    StressLevel,
    ValenceLevel,
)

__all__ = [
    "ActivityContext",
    "AffectiveState",
    "ArousalLevel",
    "Confidence",
    "DiscreteEmotion",
    "EMALabel",
    "EmotionPrediction",
    "FeatureWindow",
    "InferenceOutput",
    "QualityFlags",
    "StressLevel",
    "ValenceLevel",
]
