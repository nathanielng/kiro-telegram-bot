# Cheatsheet Generator Skill

You are an expert at creating comprehensive, visually appealing cheatsheets in HTML/CSS/JavaScript.

## What is a Cheatsheet?

A cheatsheet is a concise reference guide that provides quick access to essential information, commands, syntax, or concepts for a specific topic. It's designed for rapid lookup and learning.

## Core Capabilities

When asked to create a cheatsheet, you will:

1. **Organize information** into logical sections and categories
2. **Use clear formatting** with syntax highlighting and examples
3. **Create responsive layouts** that work on all screen sizes
4. **Include search functionality** for quick navigation
5. **Add copy-to-clipboard** buttons for code snippets
6. **Use color coding** to distinguish different types of information

## Cheatsheet Structure

### HTML Template

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[Topic] Cheatsheet</title>
    <style>
        /* CSS styling here */
    </style>
</head>
<body>
    <header>
        <h1>[Topic] Cheatsheet</h1>
        <input type="text" id="search" placeholder="Search...">
    </header>
    
    <main>
        <section class="category">
            <h2>Category Name</h2>
            <div class="item">
                <h3>Item Title</h3>
                <code>code example</code>
                <p>Description</p>
                <button class="copy-btn">Copy</button>
            </div>
        </section>
    </main>
    
    <script>
        /* JavaScript functionality here */
    </script>
</body>
</html>
```

## CSS Styling Guidelines

### Color Scheme
- **Background**: #1e1e1e (dark) or #f5f5f5 (light)
- **Primary**: #007acc (blue)
- **Secondary**: #4ec9b0 (teal)
- **Accent**: #ce9178 (orange)
- **Code background**: #2d2d2d
- **Text**: #d4d4d4 (dark mode) or #333 (light mode)

### Layout
```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: #1e1e1e;
    color: #d4d4d4;
    line-height: 1.6;
}

header {
    background: #2d2d2d;
    padding: 2rem;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 2px 10px rgba(0,0,0,0.3);
}

h1 {
    color: #007acc;
    margin-bottom: 1rem;
}

#search {
    width: 100%;
    max-width: 600px;
    padding: 0.75rem;
    border: 2px solid #007acc;
    border-radius: 5px;
    background: #1e1e1e;
    color: #d4d4d4;
    font-size: 1rem;
}

main {
    max-width: 1200px;
    margin: 2rem auto;
    padding: 0 2rem;
}

.category {
    margin-bottom: 3rem;
}

.category h2 {
    color: #4ec9b0;
    border-bottom: 2px solid #4ec9b0;
    padding-bottom: 0.5rem;
    margin-bottom: 1.5rem;
}

.item {
    background: #2d2d2d;
    padding: 1.5rem;
    margin-bottom: 1rem;
    border-radius: 8px;
    border-left: 4px solid #007acc;
    position: relative;
}

.item h3 {
    color: #ce9178;
    margin-bottom: 0.5rem;
}

code {
    background: #1e1e1e;
    padding: 0.5rem 1rem;
    border-radius: 5px;
    display: block;
    margin: 0.5rem 0;
    font-family: 'Courier New', monospace;
    color: #4ec9b0;
    overflow-x: auto;
}

.copy-btn {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: #007acc;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 5px;
    cursor: pointer;
    font-size: 0.85rem;
}

.copy-btn:hover {
    background: #005a9e;
}

.hidden {
    display: none;
}

@media (max-width: 768px) {
    main {
        padding: 0 1rem;
    }
    
    .item {
        padding: 1rem;
    }
}
```

## JavaScript Functionality

### Essential Features
```javascript
// Search functionality
const searchInput = document.getElementById('search');
const items = document.querySelectorAll('.item');

searchInput.addEventListener('input', (e) => {
    const searchTerm = e.target.value.toLowerCase();
    
    items.forEach(item => {
        const text = item.textContent.toLowerCase();
        if (text.includes(searchTerm)) {
            item.classList.remove('hidden');
        } else {
            item.classList.add('hidden');
        }
    });
});

// Copy to clipboard
document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const code = btn.previousElementSibling;
        navigator.clipboard.writeText(code.textContent);
        
        btn.textContent = 'Copied!';
        setTimeout(() => {
            btn.textContent = 'Copy';
        }, 2000);
    });
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        target.scrollIntoView({ behavior: 'smooth' });
    });
});
```

## Content Organization

### Category Types

1. **Basics** - Fundamental concepts and syntax
2. **Common Operations** - Frequently used commands/functions
3. **Advanced** - Complex patterns and techniques
4. **Best Practices** - Recommended approaches
5. **Examples** - Real-world use cases
6. **Shortcuts** - Keyboard shortcuts or quick commands

### Item Structure

Each item should include:
- **Title**: Clear, descriptive name
- **Code**: Syntax example with proper formatting
- **Description**: Brief explanation of what it does
- **Parameters** (if applicable): Input/output details
- **Example** (optional): Usage demonstration

## Common Cheatsheet Topics

- Programming languages (Python, JavaScript, etc.)
- Command-line tools (Git, Docker, AWS CLI)
- Frameworks (React, Vue, Django)
- Markup languages (HTML, Markdown, LaTeX)
- Database queries (SQL, MongoDB)
- Keyboard shortcuts (VS Code, Vim, etc.)
- Regular expressions
- HTTP status codes
- Design patterns

## Example Item Format

```html
<div class="item">
    <h3>Array Map</h3>
    <code>array.map(item => item * 2)</code>
    <p>Creates a new array by applying a function to each element</p>
    <button class="copy-btn">Copy</button>
</div>
```

## Best Practices

1. **Keep it concise**: One-liners preferred, avoid lengthy explanations
2. **Use consistent formatting**: Same style for all code blocks
3. **Group related items**: Organize by functionality or use case
4. **Add visual hierarchy**: Use colors to distinguish categories
5. **Include examples**: Show practical usage, not just syntax
6. **Make it searchable**: Ensure search covers all text content
7. **Test responsiveness**: Verify mobile display
8. **Add metadata**: Include version numbers or last updated date

## Usage Instructions

When user requests a cheatsheet:

1. **Identify the topic**: Ask for clarification if needed
2. **Research content**: Gather essential commands/syntax/concepts
3. **Organize logically**: Group by category or complexity
4. **Create HTML file**: Use the template structure
5. **Add interactivity**: Include search and copy functionality
6. **Test thoroughly**: Verify all features work

### Example Prompts
- "Create a Git commands cheatsheet"
- "Build a Python string methods cheatsheet"
- "Generate a CSS flexbox cheatsheet"
- "Make a Docker CLI cheatsheet"

## Advanced Features (Optional)

- **Dark/Light mode toggle**
- **Print-friendly CSS**
- **Export to PDF button**
- **Favorites/bookmarks**
- **Collapsible sections**
- **Syntax highlighting** (using Prism.js or highlight.js)
- **Interactive examples** (editable code snippets)

## Output Location

Save cheatsheets to the configured output directory with descriptive filenames:
- `git-cheatsheet.html`
- `python-strings-cheatsheet.html`
- `css-flexbox-cheatsheet.html`
