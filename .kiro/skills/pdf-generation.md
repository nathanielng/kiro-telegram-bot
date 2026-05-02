# PDF Generation Skill

You are an expert at generating professional PDF documents programmatically using Python's `reportlab` library.

## Core Capabilities

When asked to create a PDF, you will generate documents with:
- Titles and headings
- Paragraphs with proper text wrapping
- Bullet point lists
- Tables with styled headers and alternating row colors
- Page numbers and margins

## PDF Generation (reportlab)

```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

styles = getSampleStyleSheet()
doc = SimpleDocTemplate("output.pdf", pagesize=letter)
story = []

# Title
story.append(Paragraph("Document Title", styles['Title']))
story.append(Spacer(1, 12))

# Body text
story.append(Paragraph("Content here.", styles['BodyText']))

# Bullet points
bullet_style = ParagraphStyle('Bullet', parent=styles['BodyText'], bulletIndent=20, leftIndent=36)
story.append(Paragraph("First point", bullet_style, bulletText='•'))

# Table
data = [['Header 1', 'Header 2'], ['Cell 1', 'Cell 2']]
table = Table(data)
table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('GRID', (0, 0), (-1, -1), 1, colors.black),
]))
story.append(table)

doc.build(story)
```

## Naming Conventions

- Use lowercase filenames with hyphens: `quarterly-report.pdf`
- Include a date suffix for time-sensitive documents: `status-report-2026-05-02.pdf`

## Publishing

- **Default:** Save the file to the configured output directory.
- **If the user asks to publish:** Save to the output directory and provide the CloudFront URL: `$CLOUDFRONT_BASE_URL/$S3_PREFIX/<filename>`

## Usage

When user requests a PDF:
1. Ask for the topic/content if not specified
2. Generate the file using reportlab
3. Save the file to the configured output directory
4. If the user requested publishing, provide the CloudFront URL
5. Confirm which file was saved and its filename
