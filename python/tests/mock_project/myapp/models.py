from django.db import models


class MyModel(models.Model):
    name = models.CharField(max_length=100, help_text="The name of the item")
    description = models.TextField(blank=True, verbose_name="Item description")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "myapp"
