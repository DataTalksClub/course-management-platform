class InstructorAccessMixin:
    instructor_field = "instructor"

    def get_queryset(self, request):
        """Filter queryset based on instructor field for non-superusers."""
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            return qs.filter(**{self.instructor_field: request.user})
        return qs

    def formfield_for_foreignkey(
        self, db_field, request, obj=None, **kwargs
    ):
        """
        Filter foreign key querysets based on instructor field.
        Supports both direct fields (e.g., 'instructor') and
        related fields (e.g., 'course__instructor').
        """
        # Parse the instructor_field to handle relationships
        parts = self.instructor_field.split("__")

        # For direct instructor field on current model (no relationship traversal needed)
        if len(parts) == 1:
            return super().formfield_for_foreignkey(
                db_field, request, **kwargs
            )

        # For related fields (e.g., course__instructor)
        # parts[0] is the foreign key field name, parts[1:] is the lookup path
        fk_field_name = parts[0]
        lookup_path = "__".join(parts[1:])

        # Only apply filtering if this is the related foreign key field
        if (
            db_field.name == fk_field_name
            and not request.user.is_superuser
        ):
            # Get the related model's queryset
            related_model = db_field.remote_field.model
            kwargs["queryset"] = related_model.objects.filter(
                **{lookup_path: request.user}
            )

        return super().formfield_for_foreignkey(
            db_field, request, **kwargs
        )
