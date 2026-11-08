"""./books [slug ...] [--force]: see pdf_to_markdown.py."""
import sys

from .pdf_to_markdown import main

sys.exit(main())
