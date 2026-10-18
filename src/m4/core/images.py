"""The image files of an imaging dataset, such as MIMIC-CXR-JPG's chest X-rays.

An imaging dataset is too big to download whole (MIMIC-CXR-JPG is about half a
terabyte), so M4 downloads its tables only. One of them has a row per image,
and a path template turns such a row into the image's path below the dataset's
raw folder, which is also its path below the dataset's PhysioNet listing.
`m4 init` puts that path in a view, so that a cohort query yields the paths,
and `m4 fetch-images` downloads the images of a cohort by them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The column of the images view that holds each image's path
IMAGE_PATH_COLUMN = "image_path"

IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
QUALIFIED_NAME = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")
# {column}, or {column[:n]} for its first n characters
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?:\[:([1-9][0-9]*)\])?\}")


@dataclass(frozen=True)
class ImageFiles:
    """Where the images of a dataset are, as a template over one of its tables.

    Attributes:
        table: The table with one row per image, as `schema.table`
        view: The view M4 makes over `table`, with an `image_path` column
        id_column: The column of `table` that names one image
        path_template: The path of an image below the raw folder, with
            `{column}` for a column's value and `{column[:n]}` for its first
            n characters, e.g. files/p{subject_id[:2]}/p{subject_id}/{dicom_id}.jpg
    """

    table: str
    view: str
    id_column: str
    path_template: str

    def __post_init__(self):
        for label, name in (("table", self.table), ("view", self.view)):
            if not QUALIFIED_NAME.match(name):
                raise ValueError(
                    f"images.{label} must be a lower-case schema.name: {name!r}"
                )
        if not IDENTIFIER.match(self.id_column):
            raise ValueError(
                f"images.id_column must be a lower-case column name: {self.id_column!r}"
            )
        literal = PLACEHOLDER.sub("", self.path_template)
        if (
            not PLACEHOLDER.search(self.path_template)
            or "{" in literal
            or "}" in literal
            or "\\" in self.path_template
            or not _plain_segments(self.path_template)
        ):
            raise ValueError(
                "images.path_template must be a relative path with {column} "
                f"placeholders: {self.path_template!r}"
            )

    def _pieces(self) -> list[tuple[str, str | None, int | None]]:
        """The template as (literal text, column, prefix length) pieces."""
        pieces: list[tuple[str, str | None, int | None]] = []
        end = 0
        for match in PLACEHOLDER.finditer(self.path_template):
            column, length = match.group(1), match.group(2)
            pieces.append(
                (
                    self.path_template[end : match.start()],
                    column,
                    int(length) if length else None,
                )
            )
            end = match.end()
        pieces.append((self.path_template[end:], None, None))
        return pieces

    def path_sql(self) -> str:
        """A DuckDB expression for the path of the image a row of `table` describes.

        NULL where a column the template uses is NULL, rather than a path
        that does not exist.
        """
        terms: list[str] = []
        for literal, column, length in self._pieces():
            if literal:
                terms.append("'" + literal.replace("'", "''") + "'")
            if column is not None:
                value = 'CAST("' + column + '" AS VARCHAR)'
                terms.append(f"left({value}, {length})" if length else value)
        return " || ".join(terms)

    def path_pattern(self) -> re.Pattern[str]:
        """A pattern that the path of every image of the dataset matches in full."""
        parts: list[str] = []
        for literal, column, length in self._pieces():
            parts.append(re.escape(literal))
            if column is not None:
                parts.append(f"[^/]{{1,{length}}}" if length else "[^/]+")
        return re.compile("".join(parts))

    def is_image_path(self, path: str) -> bool:
        """Whether `path` is the path of one of the dataset's images.

        Only such a path is ever requested from the dataset's listing or
        written below its raw folder.
        """
        return bool(self.path_pattern().fullmatch(path)) and _plain_segments(path)


def _plain_segments(path: str) -> bool:
    """Whether `path` is relative and stays below the folder it is relative to."""
    return all(segment not in {"", ".", ".."} for segment in path.split("/"))
