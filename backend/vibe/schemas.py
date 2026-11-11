"""Request / response shapes. FastAPI turns these into the OpenAPI 3 spec at /openapi.json."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class TeamIn(BaseModel):
    name: str = Field(..., examples=["Techkriti Design"])
    instagram_handle: str | None = Field(None, examples=["techkriti.iitk"],
                                         description="The team's own page. Leave empty to import images by hand.")
    other_pages: list[str] = Field(default_factory=list, examples=[["antaragni.iitk", "moodi.iitb"]],
                                   description="Pages whose posts count as 'not our vibe'.")


class TeamPatch(BaseModel):
    name: str | None = None
    instagram_handle: str | None = None
    other_pages: list[str] | None = None


class FolderSpec(BaseModel):
    path: str = Field(..., description="Folder on the server machine with images (and optional meta.csv).")
    label: Literal["team", "other", "rejected"] = "team"
    source_page: str = ""


class ImportIn(BaseModel):
    fetch_instagram: bool = Field(True, description="Download the team page and other pages with Instaloader.")
    max_posts: int = Field(300, ge=1, le=5000, description="Posts to download from the team page.")
    max_posts_other: int = Field(60, ge=0, le=5000, description="Posts to download from each other page.")
    since: date | None = Field(None, description="Only download posts on or after this date (old posts reflect an old style).")
    folders: list[FolderSpec] = Field(default_factory=list)


class OutcomeIn(BaseModel):
    result: Literal["approved", "rejected", "posted"]


class PluginIn(BaseModel):
    name: str = Field(..., examples=["Contrast checker"])
    url: str = Field(..., examples=["http://localhost:8100/hook"],
                     description="We POST each event here and expect a Panel back within 5 seconds.")
    slot: Literal["result", "profile"] = Field("result", description="Where the panel shows.")
    description: str = ""
    author_team: str = ""
    team_id: int | None = Field(None, description="Only for this team; empty = every team.")


class PluginPatch(BaseModel):
    enabled: bool | None = None
    url: str | None = None
    name: str | None = None


# ---- what a plugin must answer
class PanelMetric(BaseModel):
    label: str
    value: float | int | str
    unit: str | None = None


class PanelItem(BaseModel):
    text: str
    ok: bool | None = Field(None, description="true = shown with a tick, false = with a cross, null = plain.")


class PanelPoint(BaseModel):
    label: str
    value: float


class PanelChart(BaseModel):
    type: Literal["bar", "line"] = "bar"
    title: str | None = None
    x_label: str | None = None
    y_label: str | None = None
    points: list[PanelPoint]


class Panel(BaseModel):
    """The JSON a plugin returns. Every field except title is optional."""
    title: str
    summary: str | None = None
    metrics: list[PanelMetric] | None = None
    items: list[PanelItem] | None = None
    chart: PanelChart | None = None
