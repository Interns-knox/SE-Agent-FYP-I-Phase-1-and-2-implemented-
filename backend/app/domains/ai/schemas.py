from pydantic import BaseModel, Field


class ExtractedFeature(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class FeatureExtractionResponse(BaseModel):
    features: list[ExtractedFeature]
