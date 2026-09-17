"""
Models Package
===============
Model wrappers for background removal. Each model:
- Implements a common interface (BaseModel)
- Lazy-loads weights on first inference call
- Auto-unloads after configurable TTL
- Reports capabilities without loading
"""
