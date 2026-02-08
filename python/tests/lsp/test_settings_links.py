from django_lsp.catalog import DjangoSetting


def test_setting_docs_link_version_replacement():
    setting = DjangoSetting(
        label="DEBUG",
        category="Project",
        description="Debug mode",
        example="DEBUG = True",
        default="False",
        docs_url="https://docs.djangoproject.com/en/stable/ref/settings/#debug",
    )

    # Default (stable)
    docs = setting.get_markdown_docs(django_version="stable")
    assert (
        "[Django Docs](https://docs.djangoproject.com/en/stable/ref/settings/#debug)"
        in docs
    )

    # Specific version
    docs = setting.get_markdown_docs(django_version="4.2")
    assert (
        "[Django Docs](https://docs.djangoproject.com/en/4.2/ref/settings/#debug)"
        in docs
    )

    # Another version
    docs = setting.get_markdown_docs(django_version="5.0")
    assert (
        "[Django Docs](https://docs.djangoproject.com/en/5.0/ref/settings/#debug)"
        in docs
    )
