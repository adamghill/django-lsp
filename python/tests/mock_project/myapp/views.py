from django.shortcuts import render_to_response

from .models import Book


def index(request):
    #  For testing ORM autocompletion
    book = Book.objects.filter(title="The Great Gatsby")

    return render_to_response("index.html", {"book": book})
