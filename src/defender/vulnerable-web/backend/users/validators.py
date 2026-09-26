import mimetypes
from os.path import splitext

from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


@deconstructible
class FileValidator(object):
    messages = {
        "extension_not_allowed": _(
            "Extension '%(extension)s' not allowed. Allowed extensions are: "
            "'%(allowed_extensions)s.'"
        ),
        "mimetype_not_allowed": _(
            "MIME type '%(mimetype)s' is not valid. Allowed types are: "
            "%(allowed_mimetypes)s."
        ),
        "min_size": _(
            "The current file %(size)s, which is too small. The minumum file "
            "size is %(allowed_size)s."
        ),
        "max_size": _(
            "The current file %(size)s, which is too large. The maximum file "
            "size is %(allowed_size)s."
        ),
    }

    def __init__(self, *args, **kwargs):
        self.allowed_extensions = kwargs.pop("allowed_extensions", None)
        self.allowed_mimetypes = kwargs.pop("allowed_mimetypes", None)
        self.min_size = kwargs.pop("min_size", 0)
        self.max_size = kwargs.pop("max_size", None)

    def __eq__(self, other):
        return (
            isinstance(other, FileValidator)
            and (self.allowed_extensions == other.allowed_extensions)
            and (self.allowed_mimetypes == other.allowed_mimetypes)
            and (self.min_size == other.min_size)
            and (self.max_size == other.max_size)
        )

    def __call__(self, value):
        ext = splitext(value.name)[1][1:].lower()
        if self.allowed_extensions and ext not in self.allowed_extensions:
            raise ValidationError(
                message=self.messages["extension_not_allowed"],
                params={
                    "extension": ext,
                    "allowed_extensions": ", ".join(self.allowed_extensions),
                },
                code="extension_not_allowed",
            )

        mimetype = mimetypes.guess_type(value.name)[0]
        if self.allowed_mimetypes and mimetype not in self.allowed_mimetypes:
            raise ValidationError(
                message=self.messages["mimetype_not_allowed"],
                params={
                    "mimetype": mimetype,
                    "allowed_mimetypes": ", ".join(self.allowed_mimetypes),
                },
                code="mimetype_not_allowed",
            )

        filesize = len(value)
        if self.max_size and filesize > self.max_size:
            raise ValidationError(
                message=self.messages["max_size"],
                params={
                    "size": filesizeformat(filesize),
                    "allowed_size": filesizeformat(self.max_size),
                },
                code="max_size",
            )
        elif filesize < self.min_size:
            raise ValidationError(
                message=self.messages["min_size"],
                params={
                    "size": filesizeformat(filesize),
                    "allowed_size": filesizeformat(self.min_size),
                },
                code="min_size",
            )
