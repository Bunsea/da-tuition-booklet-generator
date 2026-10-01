import os
import json
import re
import logging
from functools import lru_cache
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)


def _textbook_reference_roots() -> List[str]:
    """Return local, teacher-supplied textbook roots without bundling PDFs."""
    roots = []
    configured = os.environ.get("DA_TEXTBOOK_REFERENCE_DIR", "").strip()
    if configured:
        roots.append(configured)
    # This is the teacher's local synced folder. It is intentionally optional;
    # Streamlit Cloud simply skips it unless a matching folder is configured.
    roots.append("/Users/bunsea/My Drive/Textbooks/New Syllabus")
    return [p for p in roots if os.path.isdir(p)]


def _reference_folder_terms(textbook: str, year_level: str) -> List[str]:
    text = f"{textbook} {year_level}".lower()
    if "new senior" in text or "fitzy" in text:
        return ["New Senior Maths", "Fitzy"]
    if "standard" in text and "11" in text:
        return ["Yr11 Standard Cambridge"]
    if "extension" in text and "11" in text:
        return ["Yr11 Ext Cambridge"]
    if "advanced" in text and "9" in text:
        return ["Cambridge Yr9 Advanced"]
    if "10" in text:
        return ["Cambridge Yr10"]
    if "7" in text:
        return ["Cambridge Yr7"]
    if "9" in text:
        return ["Cambridge Yr9"]
    return []


@lru_cache(maxsize=64)
def get_textbook_exercise_reference(textbook: str, year_level: str, topic: str, max_chars: int = 14000) -> str:
    """Extract a compact, local reference excerpt from the selected textbook chapter.

    The excerpt is used as a generation reference only. Full textbook files stay
    on the teacher's machine and are never committed to the repository.
    """
    topic_tokens = [t for t in re.findall(r"[a-z0-9]+", str(topic).lower()) if len(t) >= 4]
    topic_aliases = {
        "permutations": ["combinatorics", "permutation", "combination"],
        "combinations": ["combinatorics", "permutation", "combination"],
        "binomial": ["binomial"],
        "trigonometric": ["trigonometry"],
        "differentiation": ["differentiation"],
        "probability": ["probability"],
        "statistics": ["data", "statistics"],
    }
    search_tokens = set(topic_tokens)
    for token in topic_tokens:
        search_tokens.update(topic_aliases.get(token, []))
    candidates = []
    for root in _textbook_reference_roots():
        folder_terms = _reference_folder_terms(textbook, year_level)
        matching_dirs = []
        for dp, dirs, _ in os.walk(root):
            if any(all(term.lower() in os.path.basename(dp).lower() for term in folder_terms if term) for _ in [0]):
                matching_dirs.append(dp)
        for folder in matching_dirs:
            candidates.extend(os.path.join(dp, f) for dp, _, fs in os.walk(folder) for f in fs if f.lower().endswith(".pdf"))
        if not candidates:
            candidates.extend(os.path.join(dp, f) for dp, _, fs in os.walk(root) for f in fs if f.lower().endswith(".pdf"))

    if not candidates:
        return ""
    scored = []
    for path in sorted(set(candidates)):
        name = os.path.basename(path).lower()
        score = sum(2 for token in search_tokens if token in name)
        if "answer" in name or "solution" in name or "skillsheet" in name:
            score -= 10
        scored.append((score, path))
    selected = [p for score, p in sorted(scored, key=lambda item: (-item[0], item[1])) if score > 0][:2]
    if not selected:
        non_answer = [p for score, p in scored if score > -5]
        selected = [sorted(non_answer)[0]] if non_answer else []

    try:
        from pypdf import PdfReader
        chunks = []
        for path in selected:
            reader = PdfReader(path)
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    text_parts.append(page_text)
            excerpt = "\n".join(text_parts)
            # Keep the beginning of each exercise so demonstrations follow the
            # textbook's opening progression without copying a whole chapter.
            exercise_positions = [m.start() for m in re.finditer(r"(?i)\bexercise\s+[0-9A-Za-z.]+", excerpt)]
            if exercise_positions:
                pieces = [excerpt[pos:pos + 650] for pos in exercise_positions[:32]]
                excerpt = "\n\n".join(pieces)
            chunks.append(f"SOURCE: {os.path.basename(path)}\n{excerpt[:max_chars]}")
        return "\n\n".join(chunks)[:max_chars]
    except Exception as exc:
        logger.warning("Unable to extract textbook reference: %s", exc)
        return ""


def extract_uploaded_textbook_reference(uploaded_files: List[Any], max_chars: int = 14000) -> str:
    """Extract exercise openings from teacher-uploaded textbook chapter PDFs."""
    if not uploaded_files:
        return ""
    try:
        from io import BytesIO
        from pypdf import PdfReader
        chunks = []
        for uploaded in uploaded_files:
            raw = uploaded.getvalue() if hasattr(uploaded, "getvalue") else bytes(uploaded)
            reader = PdfReader(BytesIO(raw))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            positions = [m.start() for m in re.finditer(r"(?i)\bexercise\s+[0-9A-Za-z.]+", text)]
            if positions:
                text = "\n\n".join(text[pos:pos + 650] for pos in positions[:32])
            name = getattr(uploaded, "name", "uploaded textbook chapter.pdf")
            chunks.append(f"SOURCE: {name}\n{text[:max_chars]}")
        return "\n\n".join(chunks)[:max_chars]
    except Exception as exc:
        logger.warning("Unable to extract uploaded textbook reference: %s", exc)
        return ""

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# NSW Stage 6 (2024) course boundaries:
# https://curriculum.nsw.edu.au/learning-areas/mathematics/mathematics-advanced-11-12-2024/overview/course
# https://curriculum.nsw.edu.au/learning-areas/mathematics/mathematics-extension-1-11-12-2024/overview
# Textbook chapter names are references; the NESA year-level scope takes precedence.
# --- COMPREHENSIVE CAMBRIDGE NSW CURRICULUM SYLLABUS TOPICS & SUBTOPICS ---
CAMBRIDGE_CURRICULUM: Dict[str, Dict[str, List[str]]] = {
    "Year 11 (Extension)": {
        "1. Algebra Review": [
            "1A Expanding brackets",
            "1B Factorising",
            "1C Algebraic fractions",
            "1D Solving quadratic equations",
            "1E Solving simultaneous equations"
        ],
        "2. Numbers and Surds": [
            "2A Real numbers and intervals",
            "2B Surds and their arithmetic",
            "2C Further simplification of surds",
            "2D Rationalising the denominator"
        ],
        "3. Functions and Graphs": [
            "3A Functions and function notation",
            "3B Functions, relations, and graphs",
            "3C Review of linear graphs",
            "3D Quadratic functions — factorising and the graph",
            "3E Completing the square and the graph",
            "3F The quadratic formulae and the graph",
            "3G Powers, cubics, and circles",
            "3H Two graphs that have asymptotes",
            "3I Direct and inverse variation"
        ],
        "4. Equations and Inequations": [
            "4A Linear equations and inequations",
            "4B Quadratic equations and inequations",
            "4C The discriminant",
            "4D Quadratic identities"
        ],
        "5. Transformations and Symmetry": [
            "5A Translations of known graphs",
            "5B Reflection in the y-axis and x-axis",
            "5C Even and odd symmetry",
            "5D Horizontal and vertical dilations",
            "5E The absolute value function",
            "5F Composite functions",
            "5G Combining transformations",
            "5H Continuity and piecewise-defined functions"
        ],
        "6. Further Graphs (Ext 1)": [
            "6A Solving two particular inequations",
            "6B The sign of a function",
            "6C Sketching reciprocal functions",
            "6D Sketching sums and differences",
            "6E Modifying a function using absolute value",
            "6F Inverse relations and functions",
            "6G Inverse function notation",
            "6H Defining functions and relations parametrically"
        ],
        "7. Trigonometry": [
            "7A Trigonometry with right-angled triangles",
            "7B Problems involving right-angled triangles",
            "7C Trigonometric functions of a general angle",
            "7D Quadrant, sign, and related acute angle",
            "7E Given one trigonometric function, find another",
            "7F Trigonometric identities",
            "7G Trigonometric equations",
            "7H The sine rule and the area formula",
            "7I The cosine rule",
            "7J Problems involving general triangles"
        ],
        "8. Lines in the Coordinate Plane": [
            "8A Lengths and midpoints of line segments",
            "8B Gradients of line segments and lines",
            "8C Equations of lines",
            "8D Further equations of lines",
            "8E Using pronumerals in place of numbers"
        ],
        "9. Exponential and Logarithmic Functions": [
            "9A Indices",
            "9B Fractional indices",
            "9C Logarithms",
            "9D The laws for logarithms",
            "9E Equations involving logarithms and indices",
            "9F Exponential and logarithmic graphs",
            "9G Applications of these functions"
        ],
        "10. Differentiation": [
            "10A Tangents and the derivative",
            "10B The derivative as a limit",
            "10C A rule for differentiating powers of x",
            "10D The notation dy/dx for the derivative",
            "10E The chain rule",
            "10F Differentiating powers with negative indices",
            "10G Differentiating powers with fractional indices",
            "10H The product rule",
            "10I The quotient rule",
            "10J Rates of change",
            "10K Average velocity and average speed",
            "10L Instantaneous velocity and speed"
        ],
        "11. Polynomials (Ext 1)": [
            "11A The language of polynomials",
            "11B Graphs of polynomial functions",
            "11C Division of polynomials",
            "11D The remainder and factor theorems",
            "11E Consequences of the factor theorem",
            "11F Sums and products of zeroes",
            "11G Geometry using polynomial techniques"
        ],
        "12. Euler's Number": [
            "12A The exponential function base e",
            "12B Transformations of exponential functions",
            "12C The logarithmic function base e"
        ],
        "13. Radian Measure of Angles": [
            "13A Radian measure of angle size",
            "13B Solving trigonometric equations",
            "13C Arcs and sectors of circles",
            "13D Trigonometric graphs in radians"
        ],
        "14. Probability": [
            "14A Sets and Venn diagrams",
            "14B Probability and sample spaces",
            "14C Sample space graphs and tree diagrams",
            "14D Venn diagrams and the addition theorem",
            "14E Multi-stage experiments and the product rule",
            "14F Probability tree diagrams",
            "14G Conditional probability"
        ],
        "15. Data and Probability": [
            "15A Frequency tables and data displays",
            "15B Cumulative frequency",
            "15C Grouped data"
        ],
        "16. Further Trigonometry (Ext 1)": [
            "16A Three-dimensional trigonometry",
            "16B Trigonometric functions of compound angles",
            "16C The double-angle formulae",
            "16D Trigonometric equations",
            "16E The sum of sine and cosine functions"
        ],
        "17. Combinatorics (Ext 1)": [
            "17A Factorial notation",
            "17B Ordered selections with and without repetition",
            "17C Ordered selections — three more principles",
            "17D Ordered selections with identical elements",
            "17E Counting unordered selections",
            "17F Using counting in probability",
            "17G Arrangements in a circle"
        ],
        "18. The Binomial Theorem and Pascal's Triangle (Ext 1)": [
            "18A Binomial expansions and Pascal's triangle",
            "18B Binomial expansions with several variables",
            "18C The binomial theorem",
            "18D Using the general term",
            "18E Identities in Pascal's triangle",
            "18F Further identities in Pascal's triangle"
        ]
    },
    "Year 11 (Standard)": {
        "1. Earning Money": [
            "1A Using percentages (Consolidating)",
            "1B Salaries and wages",
            "1C Annual leave loading and bonuses",
            "1D Penalty rates, overtime and special allowances",
            "1E Commission",
            "1F Piecework, royalties and government payments",
            "1G Gross pay, deductions from pay and net pay",
            "1H Allowable tax deductions which reduce taxable income",
            "1I Taxable income",
            "1J Calculating the Medicare levy and income tax payable"
        ],
        "2. Formulas and Equations": [
            "2A Substitution",
            "2B Simplifying and expanding algebraic expressions",
            "2C Linear equations",
            "2D Using equations to solve worded problems",
            "2E Using formulas to solve problems",
            "2F Changing the subject of formulas",
            "2G Distance, speed, time and stopping distance",
            "2H Blood alcohol content",
            "2I Medication dosages"
        ],
        "3. Applications of Measurement": [
            "3A Pythagoras' theorem",
            "3B Converting units of measurement",
            "3C Scientific notation and significant figures",
            "3D Perimeter, circumference and arc length",
            "3E Perimeter of composite and irregular shapes",
            "3F Area of triangles and quadrilaterals",
            "3G Area of circles and sectors",
            "3H Area of composite shapes",
            "3I Trapezoidal rule",
            "3J Surface area of right prisms",
            "3K Surface area of cylinders and spheres",
            "3L Surface area of composite solids",
            "3M Volume of right prisms",
            "3N Volume of cylinders and spheres",
            "3O Volume of pyramids and cones",
            "3P Capacity",
            "3Q Volume and capacity of composite solids"
        ],
        "4. Data Analysis 1": [
            "4A The statistical investigation process",
            "4B Classification of data",
            "4C Population and sample",
            "4D Dot plots and stem-and-leaf plots",
            "4E Line graphs, sector graphs and divided bar charts",
            "4F Ungrouped and grouped frequency tables",
            "4G Cumulative frequency",
            "4H Frequency and cumulative frequency graphs",
            "4I Real-world applications"
        ],
        "5. Linear Relationships": [
            "5A Straight-line graphs",
            "5B Gradient and y-intercept",
            "5C Using the gradient-intercept formula",
            "5D Linear modelling",
            "5E Direct variation"
        ],
        "6. Data Analysis 2": [
            "6A Measures of centre: mean, median and mode",
            "6B Measures of spread: range, IQR and standard deviation",
            "6C Outliers",
            "6D Describing the shape of a dataset",
            "6E Comparing datasets",
            "6F Parallel box plots"
        ],
        "7. Time and Location": [
            "7A Units of time",
            "7B Latitude and longitude",
            "7C Time zones",
            "7D Time difference using time zones",
            "7E Time difference using longitudes"
        ],
        "8. Managing Money": [
            "8A Percentage increase or decrease",
            "8B Calculating GST and VAT",
            "8C Buying on terms and buy now pay later schemes",
            "8D Purchasing a car",
            "8E Car insurance",
            "8F Stamp duty",
            "8G Running and maintenance costs",
            "8H Household bills",
            "8I Personal budget"
        ],
        "9. Networks, Paths and Trees": [
            "9A Networks",
            "9B Names for journeys through networks",
            "9C Constructing a network diagram",
            "9D Eulerian circuits and Hamiltonian walks",
            "9E Solving problems involving network diagrams",
            "9F Spanning trees: Prim's algorithm and Kruskal's algorithm",
            "9G Solving minimal connector problems",
            "9H Shortest path through a network"
        ]
    },
    "Year 11 (Advanced)": {
        "1. Working with Functions": [
            "1A Functions and relations",
            "1B Function notation and evaluating functions",
            "1C Domain and range",
            "1D Linear functions and graphs",
            "1E Direct and inverse variation",
            "1F Piecewise-defined functions",
            "1G Composite functions"
        ],
        "2. Numbers and Surds": [
            "2A Real numbers and intervals",
            "2B Surds and their arithmetic",
            "2C Further operations with surds",
            "2D Rationalising the denominator",
            "2E Scientific notation and significant figures"
        ],
        "3. Quadratic Functions and Equations": [
            "3A Solving quadratic equations by factorising",
            "3B Completing the square and vertex form",
            "3C The quadratic formula",
            "3D The discriminant and nature of roots",
            "3E Quadratic inequalities and graphing parabolas",
            "3F Intersection of lines and parabolas"
        ],
        "4. Linear Relationships & Coordinate Plane": [
            "4A Length, midpoint and gradient of an interval",
            "4B Equations of straight lines",
            "4C Parallel and perpendicular lines",
            "4D Perpendicular distance from a point to a line",
            "4E Intersection of lines and concurrent lines"
        ],
        "5. Transformations and Symmetry": [
            "5A Translations of graphs",
            "5B Reflections in the x- and y-axes",
            "5C Even and odd functions and symmetry",
            "5D Horizontal and vertical dilations",
            "5E Absolute value functions and equations",
            "5F Combining transformations"
        ],
        "6. Trigonometry": [
            "6A Trigonometric ratios in right-angled triangles",
            "6B Exact values of 30, 45 and 60 degrees",
            "6C Trigonometric functions for angles of any magnitude",
            "6D Trigonometric identities (Pythagorean and quotient)",
            "6E The Sine Rule and the ambiguous case",
            "6F The Cosine Rule",
            "6G Area of a triangle formula"
        ],
        "7. Radian Measure": [
            "7A Radians and degree conversion",
            "7B Arc length of a circle sector",
            "7C Area of a sector and segment of a circle",
            "7D Graphs of y = sin(x), y = cos(x), y = tan(x)",
            "7E Solving trigonometric equations in radians"
        ],
        "8. Exponential and Logarithmic Functions": [
            "8A Index laws and fractional indices",
            "8B Exponential functions and graphs",
            "8C Logarithms and logarithm laws",
            "8D Solving exponential and logarithmic equations",
            "8E Euler's number e and natural logarithms ln(x)",
            "8F Exponential growth and decay models"
        ],
        "9. Introduction to Differentiation": [
            "9A Gradients of tangents and secants",
            "9B Differentiation from first principles",
            "9C The power rule for differentiation",
            "9D Tangents and normals to curves",
            "9E Continuity and differentiability"
        ],
        "10. Probability and Data Analysis": [
            "10A Probability and sample spaces",
            "10B Addition rule and mutually exclusive events",
            "10C Multiplication rule and independent events",
            "10D Conditional probability and two-way tables",
            "10E Tree diagrams and multi-stage experiments",
            "10F Summary statistics: mean, median, IQR and standard deviation",
            "10G Box plots and outlier identification"
        ]
    },
    "Year 9": {
        "1. Computation and Financial Maths": [
            "1A Computations with integers",
            "1B Decimal places and significant figures",
            "1C Rational numbers",
            "1D Computation with fractions",
            "1E Ratios, rates and best buys",
            "1F Percentages and money",
            "1G Percentage increase and decrease",
            "1H Profits and discounts",
            "1I Income",
            "1J The PAYG income tax system",
            "1K Simple interest",
            "1L Compound interest and depreciation",
            "1M Formula for compound interest and depreciation"
        ],
        "2. Expressions, Equations and Inequalities": [
            "2A Algebraic expressions",
            "2B Simplifying algebraic expressions",
            "2C Expanding algebraic expressions",
            "2D Linear equations with pronumerals on one side",
            "2E Linear equations with brackets and pronumerals on both sides",
            "2F Solving word problems",
            "2G Linear inequalities",
            "2H Using formulas",
            "2I Linear simultaneous equations: substitution",
            "2J Linear simultaneous equations: elimination",
            "2K Solving problems with simultaneous equations",
            "2L Quadratic equations of the form ax^2 = c"
        ],
        "3. Right-Angled Triangles (Pythagoras & Trigonometry)": [
            "3A Pythagoras' theorem",
            "3B Finding the length of shorter sides",
            "3C 2D problems with Pythagoras",
            "3D 3D problems with Pythagoras",
            "3E Introducing trigonometric ratios",
            "3F Finding unknown side lengths",
            "3G Solving for the denominator",
            "3H Finding unknown angles",
            "3I Trigonometry to solve problems",
            "3J Bearings"
        ],
        "4. Linear Relationships": [
            "4A Introducing linear relationships",
            "4B Graphing straight lines using intercepts",
            "4C Lines with one intercept",
            "4D Gradient",
            "4E Gradient and direct proportion",
            "4F Gradient-intercept form",
            "4G Finding line equation y = mx + c",
            "4H Midpoint and length of a line segment",
            "4I Perpendicular lines and parallel lines",
            "4J Linear modelling",
            "4K Graphical simultaneous equations"
        ],
        "5. Length, Area, Surface Area and Volume": [
            "5A Length and perimeter",
            "5B Circle circumference and sector perimeter",
            "5C Area",
            "5D Perimeter and area of composite shapes",
            "5E Surface area of prisms and pyramids",
            "5F Surface area of cylinders",
            "5G Volume of prisms",
            "5H Volume of cylinders"
        ],
        "6. Indices and Surds": [
            "6A Index notation",
            "6B Index laws for multiplying and dividing",
            "6C Zero index and power of a power",
            "6D Index laws extended",
            "6E Negative indices",
            "6F Scientific notation",
            "6G Scientific notation with significant figures",
            "6H Fractional indices and surds",
            "6I Simple operations with surds"
        ],
        "7. Properties of Geometrical Figures": [
            "7A Angles and triangles",
            "7B Parallel lines",
            "7C Quadrilaterals and other polygons",
            "7D Congruent triangles",
            "7E Using congruence in proof",
            "7F Enlargement and similar figures",
            "7G Similar triangles",
            "7H Proving and applying similar triangles"
        ],
        "8. Quadratic Expressions & Algebraic Techniques": [
            "8A Expanding binomial products",
            "8B Perfect squares and difference of two squares",
            "8C Factorising algebraic expressions",
            "8D Factorising difference of two squares",
            "8E Factorising by grouping in pairs",
            "8F Factorising monic quadratic trinomials",
            "8G Factorising non-monic quadratic trinomials",
            "8H Simplifying algebraic fractions: mult/div",
            "8I Simplifying algebraic fractions: add/sub",
            "8J Equations involving algebraic fractions"
        ],
        "9. Probability and Single Variable Data Analysis": [
            "9A Review of probability",
            "9B Venn diagrams and two-way tables",
            "9C Using set notation",
            "9D Using arrays for two-step experiments",
            "9E Using tree diagrams",
            "9F Using relative frequencies to estimate probabilities",
            "9G Data and sampling",
            "9H Mean, median and mode",
            "9I Stem-and-leaf plots",
            "9J Grouping data into classes",
            "9K Measures of spread: range and IQR",
            "9L Box plots"
        ],
        "10. Quadratic Equations and Graphs of Parabolas": [
            "10A Quadratic equations",
            "10B Solving ax^2 + bx = 0 and x^2 - d = 0 by factorising",
            "10C Solving x^2 + bx + c = 0 by factorising",
            "10D Using quadratic equations to solve problems",
            "10E The parabola",
            "10F Sketching y = ax^2 with dilations and reflections",
            "10G Sketching translations of y = x^2",
            "10H Sketching parabolas using intercept form"
        ]
    },
    "Year 7": {
        "1. Computation with Positive Integers": [
            "1A Place value in Hindu-Arabic numbers",
            "1B Adding and subtracting positive integers",
            "1C Algorithms for adding and subtracting",
            "1D Multiplying small and large integers",
            "1E Dividing positive integers and remainders",
            "1F Estimating and rounding positive integers",
            "1G Order of operations with positive integers (BODMAS)"
        ],
        "2. Number Properties and Patterns": [
            "2A Factors and multiples",
            "2B Highest common factor and lowest common multiple",
            "2C Divisibility tests",
            "2D Prime numbers and prime decomposition",
            "2E Using indices",
            "2F Squares and square roots",
            "2G Number patterns and spatial patterns",
            "2H Tables and rules",
            "2I The Cartesian plane and graphs"
        ],
        "3. Fractions and Percentages": [
            "3A What are fractions?",
            "3B Equivalent fractions and simplified fractions",
            "3C Mixed numerals and improper fractions",
            "3D Ordering fractions",
            "3E Adding and subtracting fractions",
            "3F Multiplying and dividing fractions",
            "3G Fractions and percentages",
            "3H Percentage of a quantity",
            "3I Introduction to ratios",
            "3J Solving problems with ratios"
        ],
        "4. Algebraic Techniques": [
            "4A Introduction to formal algebra",
            "4B Substituting positive integers into algebraic expressions",
            "4C Equivalent algebraic expressions",
            "4D Like terms",
            "4E Multiplying, dividing and mixed operations",
            "4F Expanding brackets",
            "4G Applying algebra to word problems"
        ],
        "5. Decimals": [
            "5A Place value in decimals and ordering decimals",
            "5B Rounding decimals",
            "5C Addition and subtraction of decimals",
            "5D Multiplying and dividing decimals by powers of 10",
            "5E Multiplying and dividing decimals",
            "5F Connecting decimals, fractions and percentages",
            "5G Expressing proportions"
        ],
        "6. Negative Integers": [
            "6A Working with negative integers",
            "6B Adding or subtracting directed numbers",
            "6C Multiplying or dividing by an integer",
            "6D Order of operations with directed numbers",
            "6E Substitution involving negative numbers"
        ],
        "7. Angle Relationships & Geometry": [
            "7A Points, lines, intervals and angles",
            "7B Adjacent angles and vertically opposite angles",
            "7C Transversal lines and parallel lines",
            "7D Solving geometry problems with parallel lines",
            "7E Classifying and constructing triangles",
            "7F Classifying quadrilaterals and polygons",
            "7G Angle sum of a triangle and quadrilateral",
            "7H Symmetry, reflection and rotation",
            "7I Drawing solids and nets"
        ],
        "8. Statistics and Probability": [
            "8A Collecting and classifying data",
            "8B Summarising data numerically (Mean, Median, Mode, Range)",
            "8C Column graphs and dot plots",
            "8D Line graphs and stem-and-leaf plots",
            "8E Sector graphs and divided bar graphs",
            "8F Describing probability",
            "8G Theoretical probability in single-step experiments",
            "8H Experimental probability in single-step experiments"
        ],
        "9. Equations": [
            "9A Introduction to equations",
            "9B Solving equations by inspection",
            "9C Equivalent equations and systematic solving",
            "9D Equations with fractions",
            "9E Equations with brackets",
            "9F Using formulas to solve problems"
        ],
        "10. Measurement": [
            "10A Metric units of length and perimeter",
            "10B Circles, pi and circumference",
            "10C Arc length and perimeter of sectors",
            "10D Area of rectangles, parallelograms and triangles",
            "10E Area of composite shapes",
            "10F Volume of rectangular and triangular prisms",
            "10G Capacity, mass and temperature"
        ]
    },
    "Year 10 (Standard)": {
        "1. Financial Mathematics": [
            "1A Earning money and income",
            "1B Income tax and deductions",
            "1C Simple interest",
            "1D Compound interest",
            "1E Depreciation and loans"
        ],
        "2. Measurement and Geometry": [
            "2A Surface area of prisms and cylinders",
            "2B Surface area of pyramids and cones",
            "2C Volume of prisms, cylinders and pyramids",
            "2D Volume of cones and spheres",
            "2E Geometrical figures and angle properties",
            "2F Congruence and similarity in triangles"
        ],
        "3. Expressions and Indices": [
            "3A Expanding binomial expressions",
            "3B Factorising monic quadratic trinomials",
            "3C Simplifying algebraic fractions",
            "3D Index laws and negative indices",
            "3E Scientific notation"
        ],
        "4. Probability": [
            "4A Review of probability concepts",
            "4B Two-step and multi-step experiments",
            "4C Tree diagrams and arrays",
            "4D Conditional probability and dependent events"
        ],
        "5. Single and Bivariate Statistics": [
            "5A Quartiles and interquartile range (IQR)",
            "5B Box plots and identifying outliers",
            "5C Comparing parallel box plots",
            "5D Bivariate data and scatter plots",
            "5E Lines of best fit and informal correlation"
        ],
        "6. Linear and Non-linear Relationships": [
            "6A Gradient and midpoint of a line segment",
            "6B Equations of straight lines (y = mx + c)",
            "6C Graphing parabolas and key features",
            "6D Exponential graphs and growth/decay",
            "6E Hyperbolas and reciprocal curves",
            "6F Circles centred at the origin"
        ],
        "7. Networks and Graph Theory": [
            "7A Networks, vertices, edges and degrees",
            "7B Planar graphs and Euler's formula",
            "7C Walks, trails, paths, cycles and circuits",
            "7D Eulerian and Hamiltonian trails and circuits",
            "7E Weighted networks and shortest paths",
            "7F Trees, spanning trees and Prim's algorithm"
        ],
        "8. Right-Angled and Non-Right Trigonometry": [
            "8A Trigonometric ratios review",
            "8B Angles of elevation and depression",
            "8C Bearings and navigation",
            "8D The Sine Rule for finding sides and angles",
            "8E The Cosine Rule for sides and angles",
            "8F Area of any triangle using 1/2 ab sin(C)"
        ],
        "9. Equations and Formulas": [
            "9A Linear equations and inequations",
            "9B Simultaneous linear equations by substitution and elimination",
            "9C Solving quadratic equations by factorising",
            "9D Using the quadratic formula",
            "9E Rearranging formulas and changing the subject"
        ]
    },
    "Year 10 (Advanced)": {
        "1. Algebra and Equations": [
            "1A Expanding special binomial products",
            "1B Factorising monic and non-monic quadratics",
            "1C Factorising by grouping and algebraic fractions",
            "1D Solving linear equations and inequations",
            "1E Solving simultaneous linear equations",
            "1F Literal equations and changing the subject"
        ],
        "2. Surds and Indices": [
            "2A Operations with surds and simplest surd form",
            "2B Binomial products involving surds",
            "2C Rationalising the denominator",
            "2D Index laws with integer and fractional indices",
            "2E Solving exponential equations",
            "2F Introduction to logarithms and logarithmic laws"
        ],
        "3. Coordinate Geometry and Straight Lines": [
            "3A Length, midpoint and gradient of an interval",
            "3B Equations of straight lines: point-gradient and two-point form",
            "3C Parallel and perpendicular lines",
            "3D Perpendicular bisectors and distance from a point to a line"
        ],
        "4. Surface Area and Volume": [
            "4A Surface area of prisms, cylinders and pyramids",
            "4B Surface area of cones, spheres and composite solids",
            "4C Volume of prisms, cylinders, pyramids and cones",
            "4D Volume and capacity of spheres and composite solids",
            "4E Similar solids and area/volume ratios"
        ],
        "5. Quadratic Equations and Parabolas": [
            "5A Solving quadratics by factorising",
            "5B Completing the square",
            "5C The quadratic formula and exact surd roots",
            "5D The discriminant and nature of roots",
            "5E Graphing parabolas: turning point and intercept forms",
            "5F Maximum and minimum quadratic optimization",
            "5G Simultaneous linear and quadratic equations"
        ],
        "6. Advanced Trigonometry": [
            "6A Review of right-angled trigonometry",
            "6B Angles of elevation, depression and 3D trigonometry",
            "6C Bearings and true navigation",
            "6D Trigonometric ratios for angles of any magnitude",
            "6E Exact values (30, 45, 60 degrees) and quadrant signs",
            "6F The Sine Rule and the ambiguous case",
            "6G The Cosine Rule",
            "6H Area of a triangle and trigonometric identities"
        ],
        "7. Probability and Statistics": [
            "7A Review of two-step and compound probability",
            "7B Conditional probability and Venn diagrams",
            "7C Independent and dependent events",
            "7D Quartiles, IQR and parallel box plots",
            "7E Standard deviation and spread of data",
            "7F Bivariate data, scatter plots and Pearson's correlation"
        ],
        "8. Circle Geometry and Deductive Proof": [
            "8A Angle sum and exterior angle theorems in polygons",
            "8B Congruent and similar triangle proofs",
            "8C Angles at the centre and circumference of circles",
            "8D Angles in the same segment and cyclic quadrilaterals",
            "8E Tangents, chords and secant theorems",
            "8F Alternate segment theorem and geometric proofs"
        ],
        "9. Functions and Polynomials": [
            "9A Function notation, domain and range",
            "9B Transformations of functions: translations, reflections, dilations",
            "9C Cubic, hyperbolic and exponential graphs",
            "9D Direct and inverse variation",
            "9E Polynomial operations and long division",
            "9F Remainder and Factor theorems"
        ],
        "10. Networks and Graph Theory": [
            "10A Network terminology: vertices, edges, degree, loops and multiple edges",
            "10B Connected and planar graphs: Euler's formula (v - e + f = 2)",
            "10C Walks, trails, paths, circuits and cycles",
            "10D Eulerian and Hamiltonian paths and circuits",
            "10E Weighted networks and Dijkstra's / shortest path algorithm",
            "10F Trees, minimum spanning trees and Kruskal's/Prim's algorithm",
            "10G Adjacency matrices and directed networks"
        ]
    },
    "Year 12 (Advanced)": {
        "1. Sequences and Series": [
            "1A Arithmetic sequences and the nth term",
            "1B Sum of an arithmetic series",
            "1C Geometric sequences and the nth term",
            "1D Sum of a finite geometric series",
            "1E Sum to infinity of a geometric series",
            "1F Recurring decimals as geometric series"
        ],
        "2. Differential Calculus & Curve Sketching": [
            "2A The chain rule, product rule and quotient rule",
            "2B First derivative and stationary points",
            "2C Second derivative, concavity and points of inflexion",
            "2D Curve sketching with tangents and asymptotes",
            "2E Global and local maxima and minima",
            "2F Applied optimization problems"
        ],
        "3. Integral Calculus": [
            "3A Indefinite integrals and anti-differentiation",
            "3B Integrals of x^n and polynomials",
            "3C Integrals of (ax + b)^n",
            "3D Definite integrals and the fundamental theorem of calculus",
            "3E Area between a curve and the x-axis",
            "3F Area between two curves",
            "3G The trapezoidal rule for numerical approximation"
        ],
        "4. Exponential and Logarithmic Calculus": [
            "4A Differentiation of e^(f(x))",
            "4B Integration of e^(ax + b)",
            "4C Differentiation of ln(f(x))",
            "4D Integration resulting in ln(x): integrals of f'(x)/f(x)",
            "4E Exponential growth and decay differential equations"
        ],
        "5. Trigonometric Functions and Calculus": [
            "5A Graphs and properties of trigonometric functions",
            "5B Derivatives of sin(f(x)), cos(f(x)), tan(f(x))",
            "5C Integrals of sin(ax + b) and cos(ax + b)",
            "5D Integrals of sec^2(ax + b)",
            "5E Trigonometric equations and curve sketching"
        ],
        "6. Motion and Rates of Change": [
            "6A Displacement, velocity and acceleration as derivatives",
            "6B Finding velocity and displacement by integration",
            "6C Motion graphs: s-t, v-t and a-t graphs",
            "6D Rates of change and related rates in physical contexts"
        ],
        "7. Financial Mathematics (Series Applications)": [
            "7A Investments and compound interest series",
            "7B Future value of an annuity using geometric series",
            "7C Present value of an annuity using geometric series",
            "7D Superannuation balances and payouts",
            "7E Loan repayments and reducing balance mortgages"
        ],
        "8. Discrete Random Variables": [
            "8A Discrete random variables and probability distributions",
            "8B Expected value and variance of discrete random variables",
            "8C Applications of discrete probability distributions"
        ],
        "9. Continuous Random Variables": [
            "9A Continuous random variables and probability density functions (PDFs)",
            "9B Properties of PDFs: total area equals 1",
            "9C Cumulative distribution functions (CDFs)",
            "9D Expected value (mean) and median of continuous variables",
            "9E Variance and standard deviation of continuous variables"
        ],
        "10. The Normal Distribution": [
            "10A The standard normal distribution and symmetry",
            "10B Z-scores and standardising normal distributions",
            "10C Calculating normal probabilities and intervals",
            "10D The empirical 68-95-99.7 rule",
            "10E Practical applications and hypothesis testing basics"
        ]
    },
    "Year 12 (Standard)": {
        "1. Investments and Loans": [
            "1A Simple and compound interest review",
            "1B Compounding intervals and effective interest rates",
            "1C Appreciation, inflation and shares",
            "1D Reducing balance loans and repayment tables",
            "1E Credit card interest and statements"
        ],
        "2. Non-linear Relationships": [
            "2A Quadratic models and graphing parabolas",
            "2B Exponential models and growth/decay curves",
            "2C Hyperbolic and reciprocal models",
            "2D Inverse variation and inverse-square models"
        ],
        "3. Annuities": [
            "3A Future value of an annuity and formula",
            "3B Present value of an annuity and formula",
            "3C Using financial tables to calculate annuity values",
            "3D Superannuation and retirement planning"
        ],
        "4. Non-Right-Angled Trigonometry": [
            "4A Right-angled trigonometry review and bearings",
            "4B Angles of elevation and depression in 2D and 3D",
            "4C The Sine Rule for finding sides and angles",
            "4D The Cosine Rule for sides and angles",
            "4E Area of triangles using 1/2 ab sin(C)",
            "4F Radial survey maps and compass traverses"
        ],
        "5. Simultaneous Linear Equations": [
            "5A Solving simultaneous equations graphically",
            "5B Solving simultaneous equations algebraically",
            "5C Break-even analysis: cost, revenue and profit"
        ],
        "6. Bivariate Data Analysis": [
            "6A Scatter plots and forms of association",
            "6B Pearson's correlation coefficient (r)",
            "6C Line of best fit and least-squares regression line",
            "6D Interpolation, extrapolation and limitations",
            "6E Residual analysis and identifying outliers"
        ],
        "7. The Normal Distribution": [
            "7A Features of the normal distribution curve",
            "7B The 68-95-99.7 empirical rule",
            "7C Z-scores (standardised scores) and calculations",
            "7D Comparing data sets using z-scores"
        ],
        "8. Critical Path Analysis and Networks": [
            "8A Network terms: vertices, edges, paths and cycles",
            "8B Minimum spanning trees and Prim's algorithm",
            "8C Network flow: sources, sinks and cut capacity",
            "8D Activity networks and precedence tables",
            "8E Forward and backward scanning for EST and LST",
            "8F Float times and identifying the critical path"
        ]
    },
    "Year 12 (Extension 1)": {
        "1. Proof by Mathematical Induction": [
            "1A The principle of mathematical induction",
            "1B Induction proofs involving sums of series",
            "1C Induction proofs involving divisibility",
            "1D Induction proofs involving algebraic inequalities"
        ],
        "2. Vectors in 2D and 3D": [
            "2A Vectors as directed line segments and column vectors",
            "2B Vector arithmetic and linear combinations",
            "2C Magnitude, unit vectors and direction angles",
            "2D The scalar (dot) product in 2D and 3D",
            "2E Angle between two vectors and perpendicularity",
            "2F Vector projections: parallel and perpendicular components",
            "2G Geometric proofs using vector methods"
        ],
        "3. Inverse Trigonometric Functions": [
            "3A Definition and domain/range of y = arcsin(x), arccos(x), arctan(x)",
            "3B Graphs of inverse trigonometric functions",
            "3C Properties and algebraic simplifications of inverse trig functions",
            "3D Derivatives of inverse trigonometric functions",
            "3E Integrals leading to inverse trigonometric functions"
        ],
        "4. Further Trigonometric Equations": [
            "4A Compound angle identities: sin(A ± B), cos(A ± B), tan(A ± B)",
            "4B Double angle identities: sin(2A), cos(2A), tan(2A)",
            "4C The t-formulae: t = tan(theta / 2)",
            "4D Auxiliary angle method: solving a*cos(x) + b*sin(x) = c",
            "4E Products into sums and sums into products identities"
        ],
        "5. Further Calculus & Differential Equations": [
            "5A Integration by substitution (algebraic and trigonometric)",
            "5B Volumes of solids of revolution about the x- and y-axes",
            "5C First-order separable differential equations: dy/dx = f(x)g(y)",
            "5D Differential equations modelling exponential growth and decay",
            "5E Newton's law of cooling and logistic equation models"
        ],
        "6. Projectile Motion": [
            "6A Resolution of velocity and acceleration components",
            "6B Deriving equations of motion for projectile trajectory",
            "6C Time of flight, maximum height and horizontal range",
            "6D Cartesian equation of the parabolic trajectory",
            "6E Projectiles fired onto inclined planes or with air resistance models"
        ],
        "7. The Binomial Distribution": [
            "7A Bernoulli trials and binomial random variables",
            "7B Binomial probability formula: P(X = k) = nCk * p^k * (1-p)^(n-k)",
            "7C Mean and variance of a binomial distribution (mu = np, sigma^2 = npq)",
            "7D Normal approximation to the binomial distribution"
        ]
    },
    "Year 12 (Extension 2)": {
        "1. The Nature of Proof": [
            "1A Language of mathematical proof: implications, contrapositive, converse",
            "1B Proof by contradiction",
            "1C Inequalities proofs and algebraic manipulation",
            "1D The AM-GM inequality and Cauchy-Schwarz inequality",
            "1E Further induction proofs (inequalities, recurrence relations)"
        ],
        "2. Complex Numbers I - Cartesian & Polar Forms": [
            "2A Complex arithmetic, conjugate and modulus in Cartesian form",
            "2B Modulus-argument (polar) form of complex numbers",
            "2C Multiplication and division in polar form",
            "2D Geometrical representation on the Argand plane",
            "2E Loci and regions in the complex plane"
        ],
        "3. Complex Numbers II - De Moivre's Theorem & Roots": [
            "3A De Moivre's theorem for integer powers",
            "3B Applications of de Moivre's theorem to trigonometric identities",
            "3C Roots of complex numbers: solving z^n = c",
            "3D The nth roots of unity and their geometric properties",
            "3E Factorisation of polynomials over complex and real fields"
        ],
        "4. Further Vectors in Three Dimensions": [
            "4A Three-dimensional coordinate systems and basis vectors (i, j, k)",
            "4B The vector (cross) product: definition and properties",
            "4C Applications of cross product: area of triangles and parallelograms",
            "4D Vector equations of straight lines in 3D",
            "4E Vector and Cartesian equations of planes in 3D",
            "4F Intersections and shortest distance problems in 3D"
        ],
        "5. Further Integration Techniques": [
            "5A Integration by parts: indefinite and definite integrals",
            "5B Recurrence relations (reduction formulae) for integrals",
            "5C Integration using partial fractions",
            "5D Integration of trigonometric functions using Weierstrass t-substitution",
            "5E Definite integrals with symmetry and dummy variables"
        ],
        "6. Mechanics - Simple Harmonic Motion": [
            "6A Kinematics of simple harmonic motion: x'' = -w^2 x",
            "6B Velocity as a function of displacement: v^2 = w^2 (a^2 - x^2)",
            "6C Displacement-time equations: x = a*cos(wt + alpha) and x = a*sin(wt + alpha)",
            "6D Period, amplitude and maximum speed/acceleration in SHM"
        ],
        "7. Mechanics - Resisted Motion": [
            "7A Motion in a straight line under resistance proportional to velocity (-kv)",
            "7B Motion in a straight line under resistance proportional to velocity squared (-kv^2)",
            "7C Vertical motion under gravity with resistance (downward and upward)",
            "7D Terminal velocity and escape velocity"
        ]
    },
    "Year 8": {
        "1. Integers": [
            "1A Integers and the number line",
            "1B Adding and subtracting integers",
            "1C Multiplying and dividing integers",
            "1D Order of operations with integers"
        ],
        "2. Lines, Shapes and Solids": [
            "2A Angles at a point and parallel lines",
            "2B Triangles and their angle sums",
            "2C Quadrilaterals and polygons",
            "2D Three-dimensional objects and nets",
            "2E Plans and elevations"
        ],
        "3. Fractions, Decimals and Percentages": [
            "3A Operations with fractions",
            "3B Operations with decimals",
            "3C Converting fractions, decimals and percentages",
            "3D Percentages of amounts and percentage change",
            "3E Profit, loss and discount"
        ],
        "4. Measurement and Pythagoras": [
            "4A Perimeter and circumference",
            "4B Area of composite shapes and circles",
            "4C Surface area of prisms",
            "4D Volume and capacity of prisms",
            "4E Pythagoras' theorem",
            "4F Finding the length of the hypotenuse",
            "4G Finding the length of a shorter side"
        ],
        "5. Algebraic Techniques": [
            "5A The language of algebra",
            "5B Substitution and equivalence",
            "5C Adding and subtracting terms",
            "5D Multiplying and dividing terms",
            "5E Expanding brackets",
            "5F Factorising expressions",
            "5G Index laws for multiplication and division"
        ],
        "6. Ratios and Rates": [
            "6A Introducing ratios and simplifying",
            "6B Dividing quantities in a given ratio",
            "6C Scale drawings and maps",
            "6D Rates and unit rates",
            "6E Speed, distance and time"
        ],
        "7. Equations and Inequalities": [
            "7A Solving one- and two-step equations",
            "7B Equations with brackets",
            "7C Equations with pronumerals on both sides",
            "7D Solving inequalities",
            "7E Graphing inequalities on the number line",
            "7F Solving word problems with equations"
        ],
        "8. Probability and Single Variable Data": [
            "8A Theoretical probability and sample space",
            "8B Experimental probability and relative frequency",
            "8C Venn diagrams and two-way tables",
            "8D Collecting and organising data",
            "8E Dot plots, stem-and-leaf plots and histograms",
            "8F Measures of centre: mean, median, mode",
            "8G Measures of spread: range"
        ],
        "9. Straight Line Graphs": [
            "9A The Cartesian plane and plotting points",
            "9B Graphing linear relationships",
            "9C Gradient of a straight line",
            "9D The gradient-intercept form (y = mx + c)",
            "9E Horizontal and vertical lines",
            "9F Graphical solutions to linear equations"
        ],
        "10. Transformations and Congruence": [
            "10A Translations, reflections and rotations",
            "10B Congruent figures",
            "10C Congruence tests for triangles (SSS, SAS, AAS, RHS)",
            "10D Quadrilaterals and congruence proofs"
        ]
    },
    "Year 5": {
        "1. Whole Numbers & Place Value": [
            "Place value up to hundreds of thousands",
            "Rounding whole numbers",
            "Comparing and ordering numbers"
        ],
        "2. Addition and Subtraction": [
            "Mental strategies for addition and subtraction",
            "Written algorithms with regrouping",
            "Word problems involving money and measure"
        ],
        "3. Multiplication and Division": [
            "Multiplication facts up to 12 x 12",
            "Multiplying multi-digit numbers",
            "Division with and without remainders"
        ],
        "4. Fractions and Decimals": [
            "Equivalent fractions and simplifying",
            "Adding and subtracting fractions with like denominators",
            "Decimals to tenths, hundredths and thousandths"
        ],
        "5. Measurement & Geometry": [
            "Perimeter and area of rectangles",
            "Volume and capacity (litres, millilitres)",
            "2D shapes, angles and 3D objects"
        ]
    },
    "Year 6": {
        "1. Numbers and Integers": [
            "Prime and composite numbers",
            "Square and triangular numbers",
            "Negative integers on number lines"
        ],
        "2. Fractions, Decimals and Percentages": [
            "Connecting fractions, decimals and percentages",
            "Adding and subtracting fractions with unlike denominators",
            "Multiplying and dividing decimals by powers of 10"
        ],
        "3. Patterns and Pre-Algebra": [
            "Number patterns and algebraic rules",
            "Solving simple missing value equations",
            "Coordinates in the first quadrant"
        ],
        "4. Measurement & Space": [
            "Area of triangles and parallelograms",
            "Volume of rectangular prisms",
            "Angles at a point, vertically opposite angles",
            "Timetables and 24-hour time"
        ],
        "5. Chance and Data": [
            "Probabilities as fractions, decimals and percentages",
            "Interpreting line graphs and double column graphs",
            "Mean, median, mode and range"
        ]
    }
}

# Backwards compatibility alias for legacy 'Year 10' queries
CAMBRIDGE_CURRICULUM["Year 10"] = CAMBRIDGE_CURRICULUM["Year 10 (Advanced)"]

# --- COMPREHENSIVE MATHS IN FOCUS (NELSON CENGAGE / MARGARET GROVE) CURRICULUM ---
MATHS_IN_FOCUS_CURRICULUM: Dict[str, Dict[str, List[str]]] = {
    "Year 11 (Extension)": {
        "1. Algebraic Techniques": [
            "1.1 Index laws and negative/fractional indices",
            "1.2 Operations with surds and radicals",
            "1.3 Rationalising denominators",
            "1.4 Expanding brackets and special products",
            "1.5 Factorisation of quadratic and cubic expressions",
            "1.6 Algebraic fractions and operations"
        ],
        "2. Equations and Inequalities": [
            "2.1 Linear equations and inequations",
            "2.2 Quadratic equations and completing the square",
            "2.3 The quadratic formula and the discriminant",
            "2.4 Simultaneous equations (linear and quadratic)",
            "2.5 Equations involving absolute values",
            "2.6 Inequalities with absolute values and rational inequations"
        ],
        "3. Permutations, Combinations and Binomial Theorem": [
            "3.1 Fundamental counting principle and factorials",
            "3.2 Permutations of distinct and non-distinct items",
            "3.3 Arrangements in a circle and restricted permutations",
            "3.4 Combinations and selection problems",
            "3.5 Pascal's triangle and binomial coefficients",
            "3.6 The Binomial Theorem and general term expansion"
        ],
        "4. Functions and Graphs": [
            "4.1 Concept of a function and vertical line test",
            "4.2 Domain, range and function notation",
            "4.3 Linear functions, gradients and intercepts",
            "4.4 Quadratic functions and parabolic graphs",
            "4.5 Turning points and axis of symmetry",
            "4.6 Higher powers: cubics and quartics",
            "4.7 Reciprocal functions and hyperbolas",
            "4.8 Circles and semi-circles",
            "4.9 Direct and inverse variation"
        ],
        "5. Trigonometry": [
            "5.1 Trigonometric ratios in right-angled triangles",
            "5.2 Angles of elevation and depression, compass bearings",
            "5.3 Angles of any magnitude and ASTC quadrant rules",
            "5.4 Exact trigonometric values",
            "5.5 The Sine Rule and the ambiguous case",
            "5.6 The Cosine Rule and area of a triangle"
        ],
        "6. Further Functions and Relations": [
            "6.1 Composite functions and piecewise defined functions",
            "6.2 Even and odd function symmetry",
            "6.3 Asymptotes and discontinuity",
            "6.4 Graphing absolute value functions",
            "6.5 Inequalities in the Cartesian plane (regions)"
        ],
        "7. Polynomials and Inverse Functions": [
            "7.1 Polynomial definitions, degrees and operations",
            "7.2 Polynomial division and the Division Algorithm",
            "7.3 The Remainder Theorem and Factor Theorem",
            "7.4 Roots, zeros and coefficients (Vieta's formulas)",
            "7.5 Graphs of polynomials and multiple roots",
            "7.6 One-to-one functions and the horizontal line test",
            "7.7 Inverse functions: algebraic finding and reflections in y = x"
        ],
        "8. Introduction to Differentiation": [
            "8.1 Limits and limit laws",
            "8.2 Continuity and differentiability",
            "8.3 Average rate of change and gradient of a secant",
            "8.4 Differentiation from first principles",
            "8.5 The power rule for differentiation",
            "8.6 Tangents and normals to curves"
        ],
        "9. Exponential and Logarithmic Functions": [
            "9.1 Exponential functions and graphs",
            "9.2 Euler's constant e and the natural exponential",
            "9.3 Logarithm definitions and logarithmic laws",
            "9.4 Change of base formula",
            "9.5 Logarithmic graphs and vertical asymptotes",
            "9.6 Solving exponential and logarithmic equations"
        ],
        "10. Transformations of Functions": [
            "10.1 Vertical and horizontal translations",
            "10.2 Reflections across x-axis and y-axis",
            "10.3 Vertical and horizontal dilations",
            "10.4 Absolute value transformations y = |f(x)| and y = f(|x|)",
            "10.5 Combined multistep transformations"
        ],
        "11. Trigonometric Identities and Functions": [
            "11.1 Radian measure, arc length and sector area",
            "11.2 Graphs of sine, cosine and tangent functions",
            "11.3 Amplitude, period, phase shift and vertical translations",
            "11.4 Pythagorean trigonometric identities",
            "11.5 Compound angle formulas",
            "11.6 Double angle formulas",
            "11.7 The t-formulas (Weierstrass substitution)",
            "11.8 Auxiliary angle method (R cos(x - alpha))",
            "11.9 Solving trigonometric equations"
        ],
        "12. Probability and Data": [
            "12.1 Sample spaces, outcomes and probability rules",
            "12.2 Venn diagrams and the addition rule",
            "12.3 Multi-stage experiments and tree diagrams",
            "12.4 Independent events and multiplication rule",
            "12.5 Conditional probability",
            "12.6 Summary statistics: mean, median, IQR and standard deviation"
        ]
    },
    "Year 11 (Advanced)": {
        "1. Algebraic Techniques": [
            "1.1 Index laws and negative/fractional indices",
            "1.2 Operations with surds and radicals",
            "1.3 Rationalising denominators",
            "1.4 Expanding brackets and special products",
            "1.5 Factorisation of quadratic expressions",
            "1.6 Algebraic fractions and operations"
        ],
        "2. Equations and Inequalities": [
            "2.1 Linear equations and inequations",
            "2.2 Quadratic equations and completing the square",
            "2.3 The quadratic formula and the discriminant",
            "2.4 Simultaneous equations (linear and quadratic)",
            "2.5 Equations involving absolute values"
        ],
        "3. Functions and Graphs": [
            "3.1 Concept of a function and vertical line test",
            "3.2 Domain, range and function notation",
            "3.3 Linear functions, gradients and intercepts",
            "3.4 Quadratic functions and parabolic graphs",
            "3.5 Turning points and axis of symmetry",
            "3.6 Higher powers: cubics and quartics",
            "3.7 Reciprocal functions and hyperbolas",
            "3.8 Circles and semi-circles"
        ],
        "4. Trigonometry": [
            "4.1 Trigonometric ratios in right-angled triangles",
            "4.2 Angles of elevation and depression, compass bearings",
            "4.3 Angles of any magnitude and ASTC quadrant rules",
            "4.4 Exact trigonometric values",
            "4.5 The Sine Rule and the ambiguous case",
            "4.6 The Cosine Rule and area of a triangle"
        ],
        "5. Further Functions and Graphs": [
            "5.1 Composite functions and piecewise defined functions",
            "5.2 Even and odd function symmetry",
            "5.3 Asymptotes and discontinuity",
            "5.4 Graphing absolute value functions",
            "5.5 Inequalities in the Cartesian plane (regions)"
        ],
        "6. Introduction to Differentiation": [
            "6.1 Limits and limit laws",
            "6.2 Continuity and differentiability",
            "6.3 Average rate of change and gradient of a secant",
            "6.4 Differentiation from first principles",
            "6.5 The power rule for differentiation",
            "6.6 Tangents and normals to curves"
        ],
        "7. Exponential and Logarithmic Functions": [
            "7.1 Exponential functions and graphs",
            "7.2 Euler's constant e and the natural exponential",
            "7.3 Logarithm definitions and logarithmic laws",
            "7.4 Change of base formula",
            "7.5 Logarithmic graphs and vertical asymptotes",
            "7.6 Solving exponential and logarithmic equations"
        ],
        "8. Transformations of Functions": [
            "8.1 Vertical and horizontal translations",
            "8.2 Reflections across x-axis and y-axis",
            "8.3 Vertical and horizontal dilations",
            "8.4 Absolute value transformations y = |f(x)| and y = f(|x|)",
            "8.5 Combined multistep transformations"
        ],
        "9. Trigonometric Identities and Functions": [
            "9.1 Radian measure, arc length and sector area",
            "9.2 Graphs of sine, cosine and tangent functions",
            "9.3 Amplitude, period, phase shift and vertical translations",
            "9.4 Pythagorean trigonometric identities",
            "9.5 Reciprocal trigonometric functions (sec, cosec, cot)",
            "9.6 Solving trigonometric equations in radians and degrees",
            "9.7 Area of segment and applications"
        ],
        "10. Probability and Data": [
            "10.1 Sample spaces, outcomes and probability rules",
            "10.2 Venn diagrams and the addition rule",
            "10.3 Multi-stage experiments and tree diagrams",
            "10.4 Independent events and multiplication rule",
            "10.5 Conditional probability",
            "10.6 Summary statistics: mean, median, IQR and standard deviation"
        ]
    },
    "Year 11 (Standard)": {
        "1. Earning and Managing Money": [
            "1.1 Wages, salaries, overtime and allowances",
            "1.2 Commission, piecework and royalties",
            "1.3 Government allowances and pensions",
            "1.4 Allowable tax deductions and taxable income",
            "1.5 Calculating income tax and Medicare levy",
            "1.6 Budgeting and household financial planning"
        ],
        "2. Formulas and Equations": [
            "2.1 Substitution into formulas and evaluation",
            "2.2 Solving linear equations and inequations",
            "2.3 Changing the subject of a formula",
            "2.4 Direct and inverse variation equations",
            "2.5 Scientific notation and significant figures"
        ],
        "3. Measurement and Practical Calculations": [
            "3.1 Units of measurement and estimation",
            "3.2 Perimeter, circumference and arc length",
            "3.3 Area of basic shapes and composite figures",
            "3.4 Surface area of prisms, cylinders and pyramids",
            "3.5 Volume and capacity of solids",
            "3.6 Units of energy and electricity costs"
        ],
        "4. Driving Safely and Operating a Vehicle": [
            "4.1 Speed, distance and time calculations",
            "4.2 Stopping distance and reaction time",
            "4.3 Blood Alcohol Concentration (BAC) and formula calculations",
            "4.4 Fuel consumption and running costs of vehicles",
            "4.5 Vehicle purchase, stamp duty and insurance"
        ],
        "5. Collecting and Presenting Data": [
            "5.1 Types of data: categorical and numerical",
            "5.2 Frequency tables, histograms and polygons",
            "5.3 Cumulative frequency tables and ogives",
            "5.4 Dot plots and stem-and-leaf displays",
            "5.5 Misleading graphs and visual bias"
        ],
        "6. Analysing Data and Measures of Spread": [
            "6.1 Mean, median and mode from raw data and tables",
            "6.2 Range and interquartile range (IQR)",
            "6.3 Box-and-whisker plots and five-number summary",
            "6.4 Identifying outliers (1.5 x IQR rule)",
            "6.5 Comparing datasets: shape, spread and skewness"
        ],
        "7. Linear Functions and Modeling": [
            "7.1 Gradient and vertical intercept of a straight line",
            "7.2 Sketching linear graphs y = mx + c",
            "7.3 Linear models and cost/revenue/break-even analysis",
            "7.4 Simultaneous linear equations graphically and algebraically"
        ],
        "8. Networks and Paths": [
            "8.1 Network definitions: vertices, edges and faces",
            "8.2 Degree of a vertex and the Handshaking Lemma",
            "8.3 Connected, directed and weighted graphs",
            "8.4 Walks, trails, paths, cycles and circuits",
            "8.5 Eulerian and Hamiltonian trails and circuits",
            "8.6 Trees and minimum spanning trees (Prim's algorithm)"
        ],
        "9. World Locations and Times": [
            "9.1 Latitude and longitude coordinates",
            "9.2 Distances along meridians of longitude (nautical miles & km)",
            "9.3 Time zones and International Date Line calculations"
        ]
    },
    "Year 12 (Extension 2)": {
        "1. The Nature of Proof": [
            "1.1 Language of mathematical logic: propositions, implications and biconditionals",
            "1.2 Direct proofs in algebra, number theory and geometry",
            "1.3 Proof by contradiction",
            "1.4 Proof by contrapositive",
            "1.5 Disproof by counterexample",
            "1.6 Proofs of inequalities (AM-GM inequality, Cauchy-Schwarz inequality)"
        ],
        "2. Complex Numbers": [
            "2.1 Imaginary numbers and powers of i",
            "2.2 Cartesian form: operations, conjugate and modulus",
            "2.3 Division of complex numbers by multiplying by conjugate",
            "2.4 The Argand diagram and vector representation of complex numbers",
            "2.5 Modulus-argument (polar) form: z = r(cos theta + i sin theta)",
            "2.6 Products and quotients in polar form",
            "2.7 De Moivre's Theorem for integer and rational powers",
            "2.8 Exponential (Euler) form: z = r e^(i theta)",
            "2.9 Roots of complex numbers and the nth roots of unity",
            "2.10 Geometrical applications, curves and regions in the Argand plane"
        ],
        "3. 3D Vectors": [
            "3.1 3D Cartesian coordinates, distance and midpoint formulas",
            "3.2 Vectors in 3D: component form (i, j, k) and magnitude",
            "3.3 Vector operations and the scalar (dot) product in 3D",
            "3.4 Direction cosines and angles between 3D vectors",
            "3.5 Vector (cross) product and its geometric interpretation",
            "3.6 Applications of cross product: area of triangle/parallelogram and torque",
            "3.7 Vector and parametric equations of lines in 3D",
            "3.8 Vector and Cartesian equations of planes in 3D",
            "3.9 Intersections and shortest distances between lines and planes"
        ],
        "4. Further Integration": [
            "4.1 Integration by parts: single application and tabular integration",
            "4.2 Integration using partial fractions (linear and repeated factors)",
            "4.3 Trigonometric substitutions (x = a sin theta, x = a tan theta, x = a sec theta)",
            "4.4 Integration using the t-formula (Weierstrass substitution)",
            "4.5 Recurrence (reduction) formulas for indefinite and definite integrals"
        ],
        "5. Mechanics": [
            "5.1 Simple Harmonic Motion (SHM): definition and differential equation d^2x/dt^2 = -n^2 x",
            "5.2 Velocity-displacement relationship: v^2 = n^2 (a^2 - x^2)",
            "5.3 Amplitude, period, frequency, maximum velocity and acceleration in SHM",
            "5.4 Motion in a straight line with variable force and acceleration",
            "5.5 Resisted motion: resistance proportional to velocity (-kv)",
            "5.6 Resisted motion: resistance proportional to velocity squared (-kv^2)",
            "5.7 Vertical motion under gravity with air resistance and terminal velocity"
        ]
    },
    "Year 12 (Extension 1)": {
        "1. Proof by Mathematical Induction": [
            "1.1 Principle of Mathematical Induction and base steps",
            "1.2 Induction proofs for series and summations",
            "1.3 Induction proofs for divisibility",
            "1.4 Induction proofs for algebraic inequalities"
        ],
        "2. Vectors in 2D and 3D": [
            "2.1 Component notation (i, j, k) and column vectors",
            "2.2 Vector magnitude, direction and unit vectors",
            "2.3 Vector addition, subtraction and scalar multiplication",
            "2.4 The dot (scalar) product and angle between vectors",
            "2.5 Parallel, orthogonal and perpendicular vectors",
            "2.6 Vector projections (scalar projection and vector projection)",
            "2.7 Geometric proofs using vectors (medians, diagonals, orthogonality)"
        ],
        "3. Trigonometric Functions and Inverse Trig": [
            "3.1 Definitions, domains and ranges of inverse trig functions",
            "3.2 Graphs of y = arcsin x, y = arccos x, y = arctan x",
            "3.3 Derivatives of inverse trigonometric functions",
            "3.4 Integration producing inverse trigonometric functions"
        ],
        "4. Further Integration": [
            "4.1 Integration by algebraic substitution",
            "4.2 Integration using trigonometric identities (sin^2 x, cos^2 x, products)",
            "4.3 Definite integrals with substitution and updated limits"
        ],
        "5. Differential Equations": [
            "5.1 Verifying solutions to differential equations",
            "5.2 Slope fields (direction fields) and graphical solutions",
            "5.3 First-order separable differential equations",
            "5.4 The logistic growth model: dy/dt = ky(1 - y/L)"
        ],
        "6. Projectile Motion": [
            "6.1 Equations of motion with constant gravitational acceleration",
            "6.2 Horizontal and vertical velocity and displacement components",
            "6.3 Cartesian equation of the parabolic trajectory",
            "6.4 Time of flight, maximum height and horizontal range",
            "6.5 Angle of projection and trajectory optimization",
            "6.6 Projectiles launched from elevated platforms"
        ],
        "7. The Binomial Distribution and Sampling": [
            "7.1 Bernoulli trials and probability distributions",
            "7.2 The Binomial distribution: formula, expected value and variance",
            "7.3 Graphing binomial distributions and shape analysis",
            "7.4 Sample proportions and distribution of p-hat",
            "7.5 Normal approximation to the binomial distribution"
        ]
    },
    "Year 12 (Advanced)": {
        "1. Sequences and Series": [
            "1.1 Arithmetic sequences and the nth term",
            "1.2 Arithmetic series and summation formulas",
            "1.3 Geometric sequences and the nth term",
            "1.4 Geometric series and limiting sums (sum to infinity)",
            "1.5 Applications to recurring investments and superannuation",
            "1.6 Present value of annuities and reducing balance loans"
        ],
        "2. Transformation of Functions": [
            "2.1 Review of translations, dilations and reflections",
            "2.2 Composite functions and their domains/ranges",
            "2.3 Reciprocal functions y = 1/f(x)",
            "2.4 Square root functions y = sqrt(f(x))"
        ],
        "3. Differential Calculus": [
            "3.1 Chain rule for composite functions",
            "3.2 Product rule for differentiation",
            "3.3 Quotient rule for differentiation",
            "3.4 Second derivatives and higher-order rates of change"
        ],
        "4. Geometrical Applications of Differentiation": [
            "4.1 Increasing and decreasing functions",
            "4.2 Stationary points: local maxima, local minima and horizontal inflection",
            "4.3 Concavity and points of inflection",
            "4.4 Curve sketching with intercepts, stationary points and asymptotes",
            "4.5 Global extrema on closed intervals",
            "4.6 Practical optimisation and max/min problem solving"
        ],
        "5. The Exponential and Logarithmic Functions": [
            "5.1 Derivatives of y = e^x and y = e^f(x)",
            "5.2 Derivatives of y = ln x and y = ln f(x)",
            "5.3 Tangents and normals to exponential and log curves",
            "5.4 Exponential growth and decay modeling"
        ],
        "6. The Trigonometric Functions": [
            "6.1 Derivatives of sin x, cos x and tan x",
            "6.2 Derivatives of sin f(x), cos f(x) and tan f(x)",
            "6.3 Tangents, normals and stationary points of trig functions",
            "6.4 Small angle approximations (sin theta ~ theta, tan theta ~ theta)"
        ],
        "7. Integration and Areas": [
            "7.1 Indefinite integration and anti-derivatives",
            "7.2 Integration of x^n, e^x and trig functions",
            "7.3 Integration of linear composite functions",
            "7.4 Integration resulting in ln x",
            "7.5 The Fundamental Theorem of Calculus and definite integrals",
            "7.6 Area under a curve and signed areas",
            "7.7 Area between two curves",
            "7.8 Numerical integration: The Trapezoidal Rule"
        ],
        "8. Differential Equations and Rates of Change": [
            "8.1 Introduction to first-order differential equations",
            "8.2 Solving separable differential equations",
            "8.3 Exponential growth and decay models (dy/dt = ky)",
            "8.4 Modified growth models and Newton's Law of Cooling"
        ],
        "9. Random Variables and Normal Distribution": [
            "9.1 Discrete random variables and probability distributions",
            "9.2 Expected value and variance of discrete random variables",
            "9.3 Continuous random variables and probability density functions (PDF)",
            "9.4 Mean, expected value and variance of continuous distributions",
            "9.5 Cumulative distribution functions (CDF)",
            "9.6 The Normal distribution curve and empirical rule (68-95-99.7)",
            "9.7 Standard normal distribution and z-scores",
            "9.8 Calculating probabilities and percentiles from z-score tables"
        ],
        "10. Financial Mathematics": [
            "10.1 Future value of an annuity and recurrence formulas",
            "10.2 Present value of an annuity",
            "10.3 Amortisation tables and loan repayment structures",
            "10.4 Refinancing and comparison of financial packages"
        ]
    },
    "Year 12 (Standard)": {
        "1. Loans, Investments and Annuities": [
            "1.1 Compound interest and future value calculations",
            "1.2 Depreciation: straight-line and declining-balance methods",
            "1.3 Credit card interest, balances and fees",
            "1.4 Future value of an annuity using tables and formulas",
            "1.5 Present value of an annuity using tables and formulas",
            "1.6 Reducing balance loans and mortgage repayments"
        ],
        "2. Linear Functions and Modeling": [
            "2.1 Graphing linear equations and finding intercepts",
            "2.2 Direct variation and linear modeling",
            "2.3 Cost, revenue and break-even analysis",
            "2.4 Simultaneous linear equations in business contexts"
        ],
        "3. Similar Figures and Trigonometry": [
            "3.1 Similar figures, scale factors and area/volume ratios",
            "3.2 Right-angled trigonometry review and bearings",
            "3.3 The Sine Rule for sides and angles",
            "3.4 The Cosine Rule for sides and angles",
            "3.5 Area of a triangle formula: A = 1/2 ab sin C"
        ],
        "4. Rates and Ratio Analysis": [
            "4.1 Ratios and dividing quantities in given ratios",
            "4.2 Unit rates, speed, and fuel consumption",
            "4.3 Heart rate, target training zones and energy expenditure",
            "4.4 Medication dosages: Fried's, Clark's and Young's rules"
        ],
        "5. Non-linear Functions and Models": [
            "5.1 Quadratic functions and parabolic models",
            "5.2 Exponential functions and growth/decay models",
            "5.3 Hyperbolic functions and inverse variation models"
        ],
        "6. Bivariate Data and Regression": [
            "6.1 Scatter plots, dependent and independent variables",
            "6.2 Pearson's correlation coefficient (r)",
            "6.3 Line of best fit (by eye and least-squares regression line)",
            "6.4 Interpolation and extrapolation reliability",
            "6.5 Causation versus correlation"
        ],
        "7. The Normal Distribution": [
            "7.1 The bell curve and properties of the normal distribution",
            "7.2 The 68-95-99.7 empirical rule",
            "7.3 Calculating and interpreting z-scores",
            "7.4 Comparing scores across different test populations"
        ],
        "8. Critical Path Analysis and Networks": [
            "8.1 Network concepts: vertices, edges, paths and trees",
            "8.2 Weighted graphs and shortest path problems",
            "8.3 Minimum spanning trees using Prim's algorithm",
            "8.4 Activity networks, predecessors and arrow diagrams",
            "8.5 Earliest starting time (EST) and latest starting time (LST)",
            "8.6 The Critical Path and float times",
            "8.7 Network flow: source, sink, cuts and maximum flow minimum cut theorem"
        ]
    }
}

# Stage 6 Extension 1 alias
MATHS_IN_FOCUS_CURRICULUM["Year 11 (Extension 1)"] = MATHS_IN_FOCUS_CURRICULUM["Year 11 (Extension)"]

# Pearson New Senior Mathematics 4e, updated for the 2024 NSW Stage 6
# Mathematics Advanced, Extension 1 and Extension 2 syllabuses. These chapter
# titles follow Pearson's published 4e table of contents; the generator can
# expand each chapter into syllabus-specific subtopics when needed.
NEW_SENIOR_MATHEMATICS_CURRICULUM: Dict[str, Dict[str, List[str]]] = {
    "Year 11 (Advanced)": {
        f"{i}. {title}": [title] for i, title in enumerate([
            "Algebraic techniques", "Further algebraic techniques", "Functions and relations",
            "Further functions", "Trigonometry and measures of angles", "Radians",
            "Introduction to differentiation", "Exponential and logarithmic functions",
            "Probability", "Graph transformations"
        ], 1)
    },
    "Year 11 (Extension)": {
        f"{i}. {title}": [title] for i, title in enumerate([
            "Algebraic techniques", "Further algebraic techniques", "Inequalities",
            "Functions and relations", "Further functions", "Polynomials",
            "Trigonometry and measures of angles", "Radians", "Further trigonometry",
            "Probability", "Parametric equations", "Permutations and combinations",
            "Introduction to differentiation", "Exponential and logarithmic functions",
            "Binomial theorem", "Graph transformations", "Graphing functions"
        ], 1)
    },
    "Year 12 (Advanced)": {
        f"{i}. {title}": [title] for i, title in enumerate([
            "Sequences and series", "Further graph transformation and modelling",
            "Differential calculus", "Integral calculus 1", "Integral calculus 2",
            "Applications of calculus", "Random variables", "Financial mathematics"
        ], 1)
    },
    "Year 12 (Extension 1)": {
        f"{i}. {title}": [title] for i, title in enumerate([
            "Sequences and series", "Proof by mathematical induction",
            "Further graph transformation and modelling", "Vectors", "Differential calculus",
            "Integral calculus 1", "Inverse trigonometric functions", "Integral calculus 2",
            "Applications of calculus", "Motion, forces and projectiles", "Further calculus",
            "Further applications of calculus", "Random variables", "Differential equations",
            "The binomial distribution", "Financial mathematics"
        ], 1)
    },
    "Year 12 (Extension 2)": {
        f"{i}. {title}": [title] for i, title in enumerate([
            "The nature of proof", "Complex numbers", "Further work with vectors",
            "Trigonometry and integration by substitution", "Further integration", "Mechanics"
        ], 1)
    }
}
NEW_SENIOR_MATHEMATICS_CURRICULUM["Year 11 (Extension 1)"] = NEW_SENIOR_MATHEMATICS_CURRICULUM["Year 11 (Extension)"]

# Concept Mathematics (Pigeon Publishing), a new textbook series written for
# the 2026 NSW Stage 6 syllabus. The Year 11 Advanced chapter titles below are
# taken from the publisher's published sample contents; the remaining course
# maps follow the publisher's stated syllabus order until their full contents
# are published.
CONCEPT_MATHEMATICS_CURRICULUM: Dict[str, Dict[str, List[str]]] = {
    "Year 11 (Advanced)": {
        f"{i}. {title}": [title] for i, title in enumerate([
            "Algebra and Sets", "Functions", "Trigonometry",
            "Trigonometric Identities and Equations", "Introduction to Differentiation",
            "Exponential and Logarithmic Functions", "Graph Transformations", "Probability"
        ], 1)
    },
    "Year 11 (Extension)": dict(NEW_SENIOR_MATHEMATICS_CURRICULUM["Year 11 (Extension)"]),
    "Year 12 (Advanced)": dict(NEW_SENIOR_MATHEMATICS_CURRICULUM["Year 12 (Advanced)"]),
    "Year 12 (Extension 1)": dict(NEW_SENIOR_MATHEMATICS_CURRICULUM["Year 12 (Extension 1)"]),
    "Year 12 (Extension 2)": dict(NEW_SENIOR_MATHEMATICS_CURRICULUM["Year 12 (Extension 2)"]),
}
CONCEPT_MATHEMATICS_CURRICULUM["Year 11 (Extension 1)"] = CONCEPT_MATHEMATICS_CURRICULUM["Year 11 (Extension)"]

from curriculum_data import (
    NEW_CENTURY_CURRICULUM,
    MATHS_QUEST_CURRICULUM,
    SIGNPOST_CURRICULUM,
    OXFORD_CURRICULUM,
    MATHSCAPE_CURRICULUM
)

TEXTBOOK_OPTIONS = [
    "CambridgeMATHS NSW",
    "Maths in Focus (Nelson Cengage)",
    "New Century Maths (Nelson Cengage)",
    "Jacaranda Maths Quest",
    "Australian Signpost Mathematics",
    "Oxford Maths NSW",
    "New Senior Mathematics 4e (Pearson)",
    "Concept Mathematics (Pigeon Publishing)"
]

TEXTBOOK_CURRICULA: Dict[str, Dict[str, Dict[str, List[str]]]] = {
    "CambridgeMATHS NSW": CAMBRIDGE_CURRICULUM,
    "Maths in Focus (Nelson Cengage)": MATHS_IN_FOCUS_CURRICULUM,
    "New Century Maths (Nelson Cengage)": NEW_CENTURY_CURRICULUM,
    "Jacaranda Maths Quest": MATHS_QUEST_CURRICULUM,
    "Australian Signpost Mathematics": SIGNPOST_CURRICULUM,
    "Oxford Maths NSW": OXFORD_CURRICULUM,
    "New Senior Mathematics 4e (Pearson)": NEW_SENIOR_MATHEMATICS_CURRICULUM,
    "Concept Mathematics (Pigeon Publishing)": CONCEPT_MATHEMATICS_CURRICULUM,
    "Mathscape (Macmillan)": MATHSCAPE_CURRICULUM,
    # Short aliases & fuzzy matches
    "Cambridge": CAMBRIDGE_CURRICULUM,
    "CambridgeMATHS": CAMBRIDGE_CURRICULUM,
    "Maths in Focus": MATHS_IN_FOCUS_CURRICULUM,
    "Cengage": MATHS_IN_FOCUS_CURRICULUM,
    "New Century": NEW_CENTURY_CURRICULUM,
    "New Century Maths": NEW_CENTURY_CURRICULUM,
    "Maths Quest": MATHS_QUEST_CURRICULUM,
    "Jacaranda": MATHS_QUEST_CURRICULUM,
    "Signpost": SIGNPOST_CURRICULUM,
    "Singpost": SIGNPOST_CURRICULUM,
    "Australian Signpost": SIGNPOST_CURRICULUM,
    "Oxford": OXFORD_CURRICULUM,
    "Oxford Maths": OXFORD_CURRICULUM,
    "Concept Mathematics": CONCEPT_MATHEMATICS_CURRICULUM,
    "Concept": CONCEPT_MATHEMATICS_CURRICULUM,
    "Mathscape": MATHSCAPE_CURRICULUM,
    "Macmillan": MATHSCAPE_CURRICULUM,
}

def get_curriculum_dict(textbook: str = "CambridgeMATHS NSW") -> Dict[str, Dict[str, List[str]]]:
    """Retrieves the target curriculum dictionary for the given textbook series."""
    if textbook in TEXTBOOK_CURRICULA:
        return TEXTBOOK_CURRICULA[textbook]
    for tb_name, curr in TEXTBOOK_CURRICULA.items():
        if textbook.lower() in tb_name.lower() or tb_name.lower() in textbook.lower():
            return curr
    return CAMBRIDGE_CURRICULUM

def get_textbooks_for_year(year_level: str) -> List[str]:
    """
    Returns the list of valid textbook series that genuinely cover the given year level.
    Prevents showing junior-only textbooks (like Australian Signpost, Maths Quest,
    Oxford Maths NSW, Mathscape, etc.) when senior year levels (Year 11 / Year 12) are selected.
    """
    valid = []
    for tb in TEXTBOOK_OPTIONS:
        curr = get_curriculum_dict(tb)
        if year_level in curr:
            valid.append(tb)
            continue
        # Fuzzy match
        matched = False
        for yl in curr.keys():
            if year_level.lower() in yl.lower() or yl.lower() in year_level.lower():
                valid.append(tb)
                matched = True
                break
    return valid if valid else ["CambridgeMATHS NSW"]

def clean_topic_title(topic: str) -> str:
    """
    Cleans a syllabus topic title by:
    1. Removing leading year level prefixes (e.g. 'Year 12 (Advanced) Mathematics - ').
    2. Removing leading chapter/unit numbers (e.g. '1. ', '14. ', '6: ', '10A. ', 'Chapter 1 - ') without stripping '2D' or '3D'.
    3. Removing trailing labels like 'Theory Booklet', 'Worksheet', 'Homework', etc.
    4. Normalizing ' and ' or isolated 'and' to ' & '.
    5. Replacing underscores with clean spaces and normalizing whitespace.
    Runs iteratively until all prefixes and trailing tags are eliminated.
    """
    cleaned = str(topic or "").strip()
    changed = True
    while changed:
        prev = cleaned
        # Strip Year prefixes: e.g. 'Year 12 (Advanced) Mathematics - ', 'Year 11 Maths: '
        cleaned = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics|Maths)?\s*[\-\–\—\:\.]\s*', '', cleaned, flags=re.IGNORECASE).strip()
        # Strip Chapter/Unit/Topic/Part/Number prefixes: e.g. '1. ', '14. ', '6: ', '10A. ', 'Chapter 1 - ', 'Unit 2: '
        cleaned = re.sub(r'^(?:(?:Chapter|Unit|Topic|Part)\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', cleaned, flags=re.IGNORECASE).strip()
        # Strip trailing labels: e.g. ' - Homework', ' - Theory Booklet', ' — Worksheet'
        cleaned = re.sub(r'\s*[\-\–\—\:]?\s*(Theory & Practice Booklet|Theory & Notes|Theory Booklet|Practice Booklet|Booklet|Worksheet|Homework|Revision & Exam Review|Review Booklet|Review)\s*$', '', cleaned, flags=re.IGNORECASE).strip()
        # Strip leading & trailing punctuation
        cleaned = re.sub(r'^[\-\–\—\:\.\,\s]+', '', cleaned).strip()
        cleaned = re.sub(r'[\-\–\—\:\,\s]+$', '', cleaned).strip()
        changed = (cleaned != prev)

    # Normalize ' and ' to ' & '
    cleaned = re.sub(r'\band\b', '&', cleaned)
    cleaned = cleaned.replace("_", " ")
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or "Mathematics"

def format_combined_topics(topics: Union[str, List[str]]) -> str:
    """
    Formats one or more syllabus topic titles into a cohesive combined topic string.
    e.g. ['1. Algebraic Techniques'] -> 'Algebraic Techniques'
         ['1. Algebraic Techniques', '2. Equations'] -> 'Algebraic Techniques & Equations'
         ['Algebra', 'Equations', 'Trigonometry'] -> 'Algebra, Equations & Trigonometry'
    """
    if isinstance(topics, str):
        return clean_topic_title(topics)
    if not topics:
        return "Mathematics"
    cleaned_list = []
    for t in topics:
        c = clean_topic_title(t)
        if c and c not in cleaned_list:
            cleaned_list.append(c)
    if not cleaned_list:
        return "Mathematics"
    if len(cleaned_list) == 1:
        return cleaned_list[0]
    if len(cleaned_list) == 2:
        return f"{cleaned_list[0]} & {cleaned_list[1]}"
    return f"{', '.join(cleaned_list[:-1])} & {cleaned_list[-1]}"

def get_worksheet_download_filename(
    topic: str,
    sheet_type: str = "Homework",
    set_number: Optional[int] = 1,
    prefix: str = "",
    extension: str = "pdf",
    suffix: str = ""
) -> str:
    """
    Formats the worksheet download filename according to the DA Tuition convention:
    e.g. 'Sequences & Series HW Set 1.pdf'
         'Sequences & Series HW Set 1 Ans Sheet Student.pdf'
         'Sequences & Series HW Set 1 Ans Sheet Teacher.pdf'
         'DA Answer Sheet Sequences & Series HW Set 1.pdf'
         'Marking Key Sequences & Series HW Set 1.json'
         'Sequences & Series In Class Worksheet.pdf'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    clean = clean_topic_title(topic)
    if str(sheet_type).strip().lower() == "homework":
        set_str = f" Set {set_number if set_number else 1}"
        type_str = f"HW{set_str}"
    elif "mastery" in str(sheet_type).lower() or "exam" in str(sheet_type).lower():
        type_str = "End-of-Topic Mastery Exam"
    else:
        set_str = f" Set {set_number}" if (set_number and set_number > 1) else ""
        type_str = f"In Class Worksheet{set_str}" if not set_str else f"In Class{set_str}"

    p_strip = prefix.strip() if prefix else ""
    s_strip = suffix.strip() if suffix else ""

    # Legacy prefix translation: convert DA Student/Teacher Answer Sheet prefix to suffix
    if p_strip in ["DA Student Answer Sheet", "Student Answer Sheet", "Student Ans Sheet"]:
        if not s_strip:
            s_strip = "Ans Sheet Student"
        p_strip = ""
    elif p_strip in ["DA Teacher Answer Sheet", "Teacher Answer Sheet", "Teacher Ans Sheet"]:
        if not s_strip:
            s_strip = "Ans Sheet Teacher"
        p_strip = ""

    parts = []
    if p_strip:
        parts.append(p_strip)
    parts.append(clean)
    parts.append(type_str)
    if s_strip:
        parts.append(s_strip)

    fname = " ".join(parts).strip()
    fname = fname.replace("_", " ")
    fname = re.sub(r'\s+', ' ', fname)
    return f"{fname}.{extension.lstrip('.')}"

def get_topics_for_year(year_level: str, textbook: str = "CambridgeMATHS NSW") -> List[str]:
    """Returns list of pre-configured syllabus topics for a given year level and textbook."""
    curr = get_curriculum_dict(textbook)
    # Direct match
    if year_level in curr:
        return [topic for topic in curr[year_level] if is_syllabus_topic_allowed(year_level, topic)]
    
    # Fuzzy match
    for yl, topics_dict in curr.items():
        if year_level.lower() in yl.lower() or yl.lower() in year_level.lower():
            return [topic for topic in topics_dict if is_syllabus_topic_allowed(year_level, topic)]

    # Only fall back to generic list if textbook was Cambridge or alias
    if curr is CAMBRIDGE_CURRICULUM:
        return ["General Mathematics", "Algebra & Equations", "Measurement & Geometry", "Statistics & Probability"]
        
    return []


def is_syllabus_topic_allowed(year_level: str, topic: str) -> bool:
    """Keep known Year 12 topics out of 2024 NSW Year 11 topic choices."""
    text = str(topic or "")
    if is_year_11_advanced(year_level) and re.search(
        r"\b(?:discrete|continuous) random variables?\b|\bdiscrete probability distributions?\b",
        text, re.IGNORECASE
    ):
        return False
    if is_stage6_extension1(year_level) and "11" in str(year_level) and re.search(
        r"\bpigeonhole\b|\b(?:discrete|continuous) random variables?\b|\bdiscrete probability distributions?\b",
        text, re.IGNORECASE
    ):
        return False
    return True

def get_curriculum_topics(year_level: str, textbook: str = "CambridgeMATHS NSW") -> List[str]:
    """Returns list of pre-configured syllabus topics for a given year level and textbook (alias for get_topics_for_year)."""
    return get_topics_for_year(year_level, textbook=textbook)

def get_curriculum_subtopics(year_level: str, topic: str, textbook: str = "CambridgeMATHS NSW") -> List[str]:
    """Retrieves standard subtopics for a given year level, topic, and textbook."""
    curr = get_curriculum_dict(textbook)
    matched_yl_dict = None
    if year_level in curr:
        matched_yl_dict = curr[year_level]
    else:
        for yl, topics_dict in curr.items():
            if year_level.lower() in yl.lower() or yl.lower() in year_level.lower():
                matched_yl_dict = topics_dict
                break

    if matched_yl_dict:
        # Check direct topic match
        if topic in matched_yl_dict:
            return [sub for sub in matched_yl_dict[topic] if is_syllabus_topic_allowed(year_level, sub)]
        # Check partial/fuzzy match
        clean_topic = re.sub(r"^\d+[\.\s]+", "", topic).lower().strip()
        for t_name, subs in matched_yl_dict.items():
            clean_name = re.sub(r"^\d+[\.\s]+", "", t_name).lower().strip()
            if clean_topic in clean_name or clean_name in clean_topic:
                return [sub for sub in subs if is_syllabus_topic_allowed(year_level, sub)]

    # Do not borrow a similarly named Year 12 chapter for a Year 11 request.
    if re.search(r"\byear\s+1[12]\b", str(year_level), re.IGNORECASE):
        return []

    # Search across all year levels if not found
    clean_topic = re.sub(r"^\d+[\.\s]+", "", topic).lower().strip()
    for yl, topics_dict in curr.items():
        for t_name, subs in topics_dict.items():
            clean_name = re.sub(r"^\d+[\.\s]+", "", t_name).lower().strip()
            if clean_topic in clean_name or clean_name in clean_topic:
                return list(subs)

    # Fallback to Cambridge if searched in Maths in Focus and not found
    if curr is not CAMBRIDGE_CURRICULUM:
        return get_curriculum_subtopics(year_level, topic, textbook="CambridgeMATHS NSW")

    # Default fallback subtopics
    return [
        f"{topic} Core Definitions & Concepts",
        f"{topic} Key Rules & Formulae",
        f"{topic} Standard Practice Problems",
        f"{topic} Complex & Applied Word Problems"
    ]

def get_theory_booklet_download_filename(booklet: Dict[str, Any], mode: str = "student") -> str:
    """
    Formats the theory booklet download filename according to the DA Tuition convention:
    e.g. 'Sequences & Series Theory Student (Cambridge).pdf'
         'Sequences & Series Theory Teacher (Cambridge).pdf'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    topic = booklet.get("topic") or booklet.get("title") or "Mathematics"
    # Clean up leading chapter prefix (e.g. "1. ", "6: ", "10A. ", "1 ") without stripping "2D" or "3D"
    clean_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(topic)).strip()
    # Remove generic trailing phrases if present in title fallback
    clean_topic = re.sub(r'\s*(Theory & Practice Booklet|Theory Booklet|Practice Booklet|Booklet)\s*$', '', clean_topic, flags=re.IGNORECASE).strip()
    # Also remove year level prefix if it leaked into the topic (e.g. "Year 12 Mathematics - Sequences and Series")
    clean_topic = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*', '', clean_topic, flags=re.IGNORECASE).strip()
    if not clean_topic:
        clean_topic = "Mathematics"
    
    mode_str = str(mode).strip().lower()
    if mode_str == "teacher":
        mode_label = "Teacher"
    elif mode_str in ["student_class", "class", "student class", "student no space", "student_no_space"]:
        mode_label = "Student no space"
    else:
        mode_label = "Student with space"

    # Identify textbook series
    tb_raw = booklet.get("textbook") or booklet.get("curriculum_series") or ""
    if not tb_raw and "content" in booklet and isinstance(booklet["content"], dict):
        tb_raw = booklet["content"].get("textbook", "")
    if not tb_raw:
        # Check custom notes or title for textbook mentions
        combined_text = (str(booklet.get("title", "")) + " " + str(booklet.get("custom_notes", ""))).lower()
        if "focus" in combined_text:
            tb_raw = "Maths in Focus"
        elif "century" in combined_text:
            tb_raw = "New Century Maths"
        elif "quest" in combined_text:
            tb_raw = "Maths Quest"
        elif "signpost" in combined_text or "singpost" in combined_text:
            tb_raw = "Signpost"
        elif "oxford" in combined_text:
            tb_raw = "Oxford"
        elif "mathscape" in combined_text:
            tb_raw = "Mathscape"
        else:
            tb_raw = "Cambridge"
    
    tb_lower = str(tb_raw).lower()
    if "cambridge" in tb_lower:
        tb_short = "Cambridge"
    elif "maths in focus" in tb_lower or "focus" in tb_lower:
        tb_short = "Maths in Focus"
    elif "new century" in tb_lower:
        tb_short = "New Century Maths"
    elif "quest" in tb_lower:
        tb_short = "Maths Quest"
    elif "signpost" in tb_lower or "singpost" in tb_lower:
        tb_short = "Signpost"
    elif "oxford" in tb_lower:
        tb_short = "Oxford"
    elif "mathscape" in tb_lower:
        tb_short = "Mathscape"
    else:
        # Strip parenthetical annotations like '(Nelson Cengage)'
        cleaned_tb = re.sub(r'\(.*?\)', '', str(tb_raw)).strip()
        tb_short = cleaned_tb or "Cambridge"

    filename = f"{clean_topic} Theory {mode_label} ({tb_short}).pdf"
    # Remove all underscores and normalize spaces
    filename = filename.replace("_", " ")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename

def get_topic_exam_download_filename(
    exam: Dict[str, Any],
    mode: str = "student",
    extension: str = "pdf",
    theory_booklet: Optional[Dict[str, Any]] = None
) -> str:
    """
    Formats the End-of-Topic Mastery Exam download filename according to the DA Tuition convention:
    e.g. 'Functions End-of-Topic Mastery Exam Student (Cambridge).pdf'
         'Functions End-of-Topic Mastery Exam Teacher Solutions (Cambridge).pdf'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    topic = exam.get("topic") or (theory_booklet.get("topic") if theory_booklet else "") or exam.get("title") or "Mathematics"
    # Clean up leading chapter prefix (e.g. "1. ", "6: ", "10A. ", "1 ") without stripping "2D" or "3D"
    clean_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(topic)).strip()
    # Remove trailing exam phrases if present in title fallback
    clean_topic = re.sub(r'\s*(End-of-Topic Mastery Exam|Topic Mastery Exam|Mastery Exam|Exam|Worksheet)\s*$', '', clean_topic, flags=re.IGNORECASE).strip()
    # Remove year level prefix if present
    clean_topic = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*', '', clean_topic, flags=re.IGNORECASE).strip()
    if not clean_topic:
        clean_topic = "Mathematics"

    mode_str = str(mode).strip().lower()
    if mode_str in ["teacher", "solutions", "teacher_solutions", "teacher solutions"]:
        mode_label = "Teacher Solutions"
    else:
        mode_label = "Student"

    # Identify textbook series
    tb_raw = exam.get("textbook") or (theory_booklet.get("textbook") if theory_booklet else "") or exam.get("curriculum_series") or ""
    if not tb_raw and "content" in exam and isinstance(exam["content"], dict):
        tb_raw = exam["content"].get("textbook", "")
    if not tb_raw and theory_booklet and "content" in theory_booklet and isinstance(theory_booklet["content"], dict):
        tb_raw = theory_booklet["content"].get("textbook", "")
    if not tb_raw:
        combined_text = (str(exam.get("title", "")) + " " + str(exam.get("custom_instructions", "")) + " " + str(theory_booklet.get("title", "") if theory_booklet else "")).lower()
        if "focus" in combined_text:
            tb_raw = "Maths in Focus"
        elif "century" in combined_text:
            tb_raw = "New Century Maths"
        elif "quest" in combined_text:
            tb_raw = "Maths Quest"
        elif "signpost" in combined_text or "singpost" in combined_text:
            tb_raw = "Signpost"
        elif "oxford" in combined_text:
            tb_raw = "Oxford"
        elif "mathscape" in combined_text:
            tb_raw = "Mathscape"
        else:
            tb_raw = "Cambridge"

    tb_lower = str(tb_raw).lower()
    if "cambridge" in tb_lower:
        tb_short = "Cambridge"
    elif "maths in focus" in tb_lower or "focus" in tb_lower:
        tb_short = "Maths in Focus"
    elif "new century" in tb_lower:
        tb_short = "New Century Maths"
    elif "quest" in tb_lower:
        tb_short = "Maths Quest"
    elif "signpost" in tb_lower or "singpost" in tb_lower:
        tb_short = "Signpost"
    elif "oxford" in tb_lower:
        tb_short = "Oxford"
    elif "mathscape" in tb_lower:
        tb_short = "Mathscape"
    else:
        cleaned_tb = re.sub(r'\(.*?\)', '', str(tb_raw)).strip()
        tb_short = cleaned_tb or "Cambridge"

    ext = extension.lstrip(".")
    filename = f"{clean_topic} End-of-Topic Mastery Exam {mode_label} ({tb_short}).{ext}"
    filename = filename.replace("_", " ")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename


def get_worksheet_download_filename(
    worksheet: Optional[Union[Dict[str, Any], str]] = None,
    sheet_type: str = "Homework",
    mode: str = "student",
    extension: str = "pdf",
    theory_booklet: Optional[Dict[str, Any]] = None,
    topic: Optional[str] = None,
    set_number: Optional[int] = 1,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None
) -> str:
    """
    Formats download filenames for worksheets according to DA Tuition conventions.
    Supports both:
    1. Legacy signature: get_worksheet_download_filename(topic="...", sheet_type="...", set_number=1, prefix="...", suffix="...")
    2. Dict signature: get_worksheet_download_filename(worksheet_dict, sheet_type="...", mode="student", theory_booklet=...)
    Strictly removes all '_' and replaces them with clean spaces.
    """
    if topic is not None or isinstance(worksheet, str):
        raw_topic = topic if topic is not None else str(worksheet)
        clean = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(raw_topic)).strip()
        clean = clean.replace(" and ", " & ")

        st_lower = str(sheet_type).lower()
        if "in-class" in st_lower or "in_class" in st_lower or "in class" in st_lower:
            type_str = "In Class Worksheet"
        elif "mastery" in st_lower or "exam" in st_lower:
            type_str = "End-of-Topic Mastery Exam"
        else:
            type_str = f"HW Set {set_number or 1}"

        p_strip = str(prefix).strip() if prefix else ""
        s_strip = str(suffix).strip() if suffix else ""

        # Legacy prefix translation: convert DA Student/Teacher Answer Sheet prefix to suffix
        if p_strip in ["DA Student Answer Sheet", "Student Answer Sheet", "Student Ans Sheet"]:
            if not s_strip:
                s_strip = "Ans Sheet Student"
            p_strip = ""
        elif p_strip in ["DA Teacher Answer Sheet", "Teacher Answer Sheet", "Teacher Ans Sheet"]:
            if not s_strip:
                s_strip = "Ans Sheet Teacher"
            p_strip = ""

        parts = []
        if p_strip:
            parts.append(p_strip)
        parts.append(clean)
        parts.append(type_str)
        if s_strip:
            parts.append(s_strip)

        filename = f"{' '.join(parts)}.{extension.lstrip('.')}"
        filename = filename.replace("_", " ")
        filename = re.sub(r'\s+', ' ', filename).strip()
        return filename

    ws = worksheet or {}
    t_val = ws.get("topic") or (theory_booklet.get("topic") if theory_booklet else "") or ws.get("title") or "Mathematics"
    clean_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(t_val)).strip()
    clean_topic = re.sub(r'\s*(End-of-Topic Mastery Exam|Topic Mastery Exam|Mastery Exam|Exam|In-Class Practice|In-Class Exercise|In-Class|Homework|Worksheet)\s*$', '', clean_topic, flags=re.IGNORECASE).strip()
    clean_topic = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*', '', clean_topic, flags=re.IGNORECASE).strip()
    if not clean_topic:
        clean_topic = "Mathematics"

    st_raw = (ws.get("assessment_type") or ws.get("sheet_type") or sheet_type or "homework").lower()
    eff_set_num = ws.get("set_number", set_number) or set_number or 1

    if "in_class" in st_raw or "in-class" in st_raw or "class" in st_raw:
        type_label = "In-Class Exercise"
    elif "topic_exam" in st_raw or "exam" in st_raw:
        type_label = "End-of-Topic Mastery Exam"
    else:
        type_label = f"Homework Set {eff_set_num}"

    mode_str = str(mode).strip().lower()
    if mode_str in ["teacher", "solutions", "teacher_solutions", "teacher solutions"]:
        mode_label = "Teacher Solutions"
    elif mode_str in ["answers", "answer_sheet", "quick_answers", "quick answers"]:
        mode_label = "Quick Answers"
    else:
        mode_label = "Student"

    # Identify textbook series
    tb_raw = ws.get("textbook") or (theory_booklet.get("textbook") if theory_booklet else "") or ws.get("curriculum_series") or ""
    if not tb_raw and "content" in ws and isinstance(ws["content"], dict):
        tb_raw = ws["content"].get("textbook", "")
    if not tb_raw and theory_booklet and "content" in theory_booklet and isinstance(theory_booklet["content"], dict):
        tb_raw = theory_booklet["content"].get("textbook", "")
    if not tb_raw:
        combined_text = (str(ws.get("title", "")) + " " + str(ws.get("custom_instructions", ""))).lower()
        if "focus" in combined_text:
            tb_raw = "Maths in Focus"
        elif "century" in combined_text:
            tb_raw = "New Century Maths"
        elif "quest" in combined_text:
            tb_raw = "Maths Quest"
        elif "signpost" in combined_text or "singpost" in combined_text:
            tb_raw = "Signpost"
        elif "oxford" in combined_text:
            tb_raw = "Oxford"
        elif "mathscape" in combined_text:
            tb_raw = "Mathscape"
        else:
            tb_raw = "Cambridge"

    tb_lower = str(tb_raw).lower()
    if "cambridge" in tb_lower:
        tb_short = "Cambridge"
    elif "maths in focus" in tb_lower or "focus" in tb_lower:
        tb_short = "Maths in Focus"
    elif "new century" in tb_lower:
        tb_short = "New Century Maths"
    elif "quest" in tb_lower:
        tb_short = "Maths Quest"
    elif "signpost" in tb_lower or "singpost" in tb_lower:
        tb_short = "Signpost"
    elif "oxford" in tb_lower:
        tb_short = "Oxford"
    elif "mathscape" in tb_lower:
        tb_short = "Mathscape"
    else:
        cleaned_tb = re.sub(r'\(.*?\)', '', str(tb_raw)).strip()
        tb_short = cleaned_tb or "Cambridge"

    ext = extension.lstrip(".")
    filename = f"{clean_topic} {type_label} {mode_label} ({tb_short}).{ext}"
    filename = filename.replace("_", " ")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename

def get_review_booklet_download_filename(booklet: Dict[str, Any], mode: str = "student", prefix: Optional[str] = None, extension: str = "pdf") -> str:
    """
    Formats the review booklet download filename:
    e.g. 'Sequences & Series Review Student (Cambridge).pdf'
         'DA Student Answer Sheet Sequences & Series Review (Cambridge).pdf'
         'DA Teacher Answer Sheet Sequences & Series Review (Cambridge).pdf'
         'Marking Key Sequences & Series Review (Cambridge).json'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    topic = booklet.get("topic") or booklet.get("title") or "Mathematics"
    clean_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(topic)).strip()
    clean_topic = re.sub(r'\s*(Topic Review & Exam Revision Booklet|Review & Exam Revision Booklet|Topic Review Booklet|Review Booklet|Revision Booklet|Booklet)\s*$', '', clean_topic, flags=re.IGNORECASE).strip()
    clean_topic = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*', '', clean_topic, flags=re.IGNORECASE).strip()
    if not clean_topic:
        clean_topic = "Mathematics"

    mode_str = str(mode).strip().lower()

    tb_raw = booklet.get("textbook") or booklet.get("curriculum_series") or ""
    if not tb_raw and "content" in booklet and isinstance(booklet["content"], dict):
        tb_raw = booklet["content"].get("textbook", "")
    if not tb_raw:
        combined_text = (str(booklet.get("title", "")) + " " + str(booklet.get("custom_notes", ""))).lower()
        if "focus" in combined_text:
            tb_raw = "Maths in Focus"
        elif "century" in combined_text:
            tb_raw = "New Century Maths"
        elif "quest" in combined_text:
            tb_raw = "Maths Quest"
        elif "signpost" in combined_text or "singpost" in combined_text:
            tb_raw = "Signpost"
        elif "oxford" in combined_text:
            tb_raw = "Oxford"
        elif "mathscape" in combined_text:
            tb_raw = "Mathscape"
        else:
            tb_raw = "Cambridge"

    tb_lower = str(tb_raw).lower()
    if "cambridge" in tb_lower:
        tb_short = "Cambridge"
    elif "maths in focus" in tb_lower or "focus" in tb_lower:
        tb_short = "Maths in Focus"
    elif "new century" in tb_lower:
        tb_short = "New Century Maths"
    elif "quest" in tb_lower:
        tb_short = "Maths Quest"
    elif "signpost" in tb_lower or "singpost" in tb_lower:
        tb_short = "Signpost"
    elif "oxford" in tb_lower:
        tb_short = "Oxford"
    elif "mathscape" in tb_lower:
        tb_short = "Mathscape"
    else:
        cleaned_tb = re.sub(r'\(.*?\)', '', str(tb_raw)).strip()
        tb_short = cleaned_tb or "Cambridge"

    ext = extension.lstrip(".")

    if prefix:
        filename = f"{prefix} {clean_topic} Review ({tb_short}).{ext}"
    elif mode_str in ["student_answer_sheet", "student_ans", "answer_sheet"]:
        filename = f"DA Student Answer Sheet {clean_topic} Review ({tb_short}).{ext}"
    elif mode_str in ["teacher_answer_sheet", "teacher_ans", "sample_answer_sheet", "sample_ans"]:
        filename = f"DA Teacher Answer Sheet {clean_topic} Review ({tb_short}).{ext}"
    elif mode_str in ["marking_key", "key"]:
        filename = f"Marking Key {clean_topic} Review ({tb_short}).{ext}"
    else:
        if mode_str == "teacher":
            mode_label = "Teacher"
        elif mode_str in ["student_class", "class", "student class", "student no space", "student_no_space"]:
            mode_label = "Student no space"
        else:
            mode_label = "Student with space"
        filename = f"{clean_topic} Review {mode_label} ({tb_short}).{ext}"

    filename = filename.replace("_", " ")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename



def is_year_11_advanced(year_level: str) -> bool:
    """
    Returns True if the year level corresponds specifically to NSW Year 11 Mathematics Advanced (2-Unit).
    Excludes Extension courses, Standard Mathematics, and junior years.
    """
    yl = str(year_level).strip().lower()
    if "11" not in yl:
        return False
    if "ext" in yl or "standard" in yl or "std" in yl:
        return False
    return "adv" in yl or yl in ["year 11", "yr 11", "year 11 maths", "year 11 mathematics"]


def is_stage4(year_level: str) -> bool:
    """Returns True if year level is Stage 4 (Year 7 or Year 8)."""
    yl = str(year_level).strip().lower()
    return any(k in yl for k in ["year 7", "yr 7", "year 8", "yr 8", "stage 4", "7th grade", "8th grade"])


def is_stage5(year_level: str) -> bool:
    """Returns True if year level is Stage 5 (Year 9 or Year 10)."""
    yl = str(year_level).strip().lower()
    return any(k in yl for k in ["year 9", "yr 9", "year 10", "yr 10", "stage 5", "5.1", "5.2", "5.3", "9th grade", "10th grade"])


def is_stage6_standard(year_level: str) -> bool:
    """Returns True if year level is Stage 6 Standard Mathematics (Standard 1 or Standard 2)."""
    yl = str(year_level).strip().lower()
    return ("11" in yl or "12" in yl or "stage 6" in yl) and ("standard" in yl or "std" in yl)


def is_stage6_extension1(year_level: str) -> bool:
    """Returns True if year level is Stage 6 Mathematics Extension 1."""
    yl = str(year_level).strip().lower()
    is_extension_one = any(k in yl for k in ("ext 1", "extension 1", "ext1", "3 unit", "3u"))
    is_unsuffixed_extension = bool(re.search(r"\bextension\b", yl)) and not is_stage6_extension2(year_level)
    return ("11" in yl or "12" in yl or "stage 6" in yl) and (is_extension_one or is_unsuffixed_extension)


def is_stage6_extension2(year_level: str) -> bool:
    """Returns True if year level is Stage 6 Mathematics Extension 2."""
    yl = str(year_level).strip().lower()
    return ("12" in yl or "stage 6" in yl) and ("ext 2" in yl or "extension 2" in yl or "ext2" in yl or "4 unit" in yl or "4u" in yl)


def get_stage6_syllabus_boundary_prompt(year_level: str, topic: str = "") -> str:
    """
    Generates strict syllabus boundary directives and negative constraints for AI generation.
    Strictly aligns all content (theory, examples, practice questions) to the NSW NESA Mathematics Syllabus.
    Guarantees ZERO out-of-syllabus leakage or inappropriate university/tertiary notation.
    """
    yl = str(year_level).strip().lower()

    # 1. STAGE 4 (Years 7-8)
    if is_stage4(year_level):
        return """
STRICT NSW NESA SYLLABUS BOUNDARY DIRECTIVE (STAGE 4: YEARS 7-8) - ZERO TOLERANCE LEAKAGE:
The content generated is strictly for NSW Stage 4 (Years 7-8) Mathematics.
1. PERMITTED STAGE 4 TOPICS ONLY:
- Integers, fractions, decimals, percentages, ratios, rates.
- Algebraic expressions, combining like terms, expanding single brackets $a(b+c)$, factorising common numeric factors.
- Solving 1-step and 2-step linear equations.
- Cartesian plane (plotting coordinates in 4 quadrants, table of values for simple lines).
- Perimeter, circumference of circles, area of simple shapes (triangles, rectangles, parallelograms, trapeziums, circles).
- Volume of right prisms (cubes, rectangular prisms, triangular prisms).
- Angles: complementary, supplementary, vertically opposite, angles on a straight line, angle sum of triangle (180°), quadrilateral (360°), parallel lines (alternate, corresponding, co-interior).
- Basic single-event probability (sample spaces, $P(E) = \\frac{\\text{favourable}}{\\text{total}}$).
- Univariate statistics: dot plots, stem-and-leaf, column graphs, mean, median, mode, range.

2. STRICT NEGATIVE CONSTRAINTS (STRICTLY FORBIDDEN FOR STAGE 4):
- STRICTLY NO QUADRATICS: NO quadratic equations, quadratic formula, parabolas, or factorising trinomials.
- STRICTLY NO PYTHAGORAS: NO $a^2 + b^2 = c^2$ (Pythagoras is strictly Stage 5).
- STRICTLY NO TRIGONOMETRY: NO sine, cosine, tangent ($\\sin, \\cos, \\tan$), SOH CAH TOA, or bearings.
- STRICTLY NO SURDS: NO irrational roots, simplifying surds, or rationalising denominators.
- STRICTLY NO SIMULTANEOUS EQUATIONS.
- STRICTLY NO COORDINATE GEOMETRY FORMULAS: NO distance formula, midpoint formula, gradient formula $m = \\frac{y_2-y_1}{x_2-x_1}$, or line equation $y = mx + b$.
- STRICTLY NO NEGATIVE OR FRACTIONAL INDICES (only non-negative integer powers).
- STRICTLY NO CALCULUS, LOGARITHMS, VECTORS, OR ADVANCED NOTATION (e.g. absolutely NO summation notation $\\sum$).
"""

    # 2. STAGE 5 (Years 9-10: 5.1 / 5.2 / 5.3)
    if is_stage5(year_level):
        return """
STRICT NSW NESA SYLLABUS BOUNDARY DIRECTIVE (STAGE 5: YEARS 9-10) - ZERO TOLERANCE LEAKAGE:
The content generated is strictly for NSW Stage 5 (Years 9-10: 5.1/5.2/5.3) Mathematics.
1. PERMITTED STAGE 5 TOPICS:
- Financial Mathematics: earning, simple interest, compound interest, depreciation.
- Indices & Surds: index laws (incl. negative & fractional indices in 5.3), scientific notation, surd operations, rationalising denominators (5.3).
- Algebraic Techniques: expanding & factorising quadratics (monic & non-monic for 5.3, difference of two squares), algebraic fractions.
- Equations: linear equations & inequalities, simultaneous linear equations, quadratic equations (factoring, completing the square, quadratic formula).
- Linear & Non-Linear Graphs: gradient, midpoint, distance, line equations ($y=mx+b$, $ax+by+c=0$), parabolas ($y=ax^2$), hyperbolas ($y=k/x$), circles ($x^2+y^2=r^2$), cubics ($y=ax^3$).
- Trigonometry: right-angled trig (SOH CAH TOA, angles of elevation/depression, bearings), non-right-angled trig (Sine Rule, Cosine Rule, Area $A = \\frac{1}{2}ab\\sin C$ for 5.3).
- Measurement: surface area and volume of cylinders, cones, spheres, pyramids, composite solids.
- Probability & Statistics: two-way tables, tree diagrams, Venn diagrams, mean, median, mode, IQR, standard deviation, box plots, bivariate scatter plots.
- Networks & Graph Theory: vertices, edges, vertex degrees, paths, cycles, Eulerian and Hamiltonian trails/circuits, trees, minimum spanning trees (Prim's/Kruskal's algorithm).

2. STRICT NEGATIVE CONSTRAINTS (STRICTLY FORBIDDEN FOR STAGE 5 - ZERO TOLERANCE):
- STRICTLY NO CALCULUS: NO derivatives ($f'(x)$, $\\frac{dy}{dx}$), limits ($\\lim$), integrals ($\\int$), tangents/normals via calculus.
- STRICTLY NO RADIANS: All angles MUST be in degrees (°). Radian measure is strictly Stage 6 Advanced.
- STRICTLY NO LOGARITHMS: NO $\\log$, $\\ln$, or natural base $e$.
- STRICTLY NO SIGMA / SUMMATION NOTATION ($\\sum$, $\\Sigma$, ∑):
  * Year 10 NSW students have NEVER learned sigma notation!
  * For Networks: State the Handshaking Lemma as 'Sum of degrees = 2 × number of edges' or $\\text{Sum of degrees} = 2e$. NEVER write $\\sum \\deg(v) = 2e$.
  * For Statistics: Write 'Sum of scores' or 'Sum of values', NEVER $\\sum x$ or $\\sum fx$. Write $\\text{Mean} = \\frac{\\text{Sum of scores}}{\\text{Total frequency}}$.
- STRICTLY NO SEQUENCES & SERIES FORMULAS: NO $T_n = a + (n-1)d$, NO geometric series, NO summation formulas.
- STRICTLY NO VECTORS OR COMPLEX NUMBERS.
- STRICTLY NO TERTIARY / UNIVERSITY NOTATION (e.g. $\\forall, \\exists, \\subset, \\setminus$).
- STRICTLY NO ABSOLUTE VALUE OF Y ($|y|$).
"""

    # 3. STAGE 6 MATHEMATICS STANDARD (Years 11-12)
    if is_stage6_standard(year_level):
        return """
STRICT NSW NESA SYLLABUS BOUNDARY DIRECTIVE (STAGE 6 MATHEMATICS STANDARD 1 & 2) - ZERO TOLERANCE LEAKAGE:
The content generated is strictly for NSW Stage 6 Mathematics Standard (non-calculus pathway).
1. PERMITTED STANDARD MATHEMATICS TOPICS:
- Financial Mathematics: earning and managing money, taxation (PAYG, Medicare levy, tax tables), budgeting, household expenses, simple and compound interest, reducing balance loans, recurrence relations, annuities (future and present value tables).
- Measurement: applications of measurement, non-right-angled trigonometry (Sine Rule, Cosine Rule, Area of triangle), spherical geometry/angles, trapezoidal rule for estimation of irregular areas.
- Statistical Analysis: univariate data summary, standard deviation, normal distribution (empirical rule 68-95-99.7, z-scores), bivariate data (scatter plots, Pearson's correlation coefficient $r$, line of best fit $y = mx + c$, interpolation/extrapolation).
- Networks: network concepts (vertices, edges, weights, degrees, walk, trail, path, circuit, cycle), planar graphs and Euler's formula ($V - E + F = 2$), Eulerian and Hamiltonian paths/circuits, shortest path problems, minimum spanning trees (Prim's algorithm), critical path analysis (activity tables, forward/backward scanning, float times, critical paths), network flow (source, sink, capacity, cuts, max-flow min-cut theorem), Hungarian algorithm for assignment.

2. STRICT NEGATIVE CONSTRAINTS (STRICTLY FORBIDDEN FOR STANDARD MATHEMATICS):
- STRICTLY NO CALCULUS: Under NO circumstances should differentiation, anti-derivatives, definite integrals, or limits appear.
- STRICTLY NO RADIANS: All angles must be in degrees.
- STRICTLY NO LOGARITHMIC FUNCTIONS OR EXPONENTIAL BASE $e$: No $\\ln x$, $\\log_a x$, or $e^x$ calculus models.
- STRICTLY NO CONTINUOUS PROBABILITY DISTRIBUTIONS (PDFs/CDFs): Only normal distribution z-scores and empirical rule.
- STRICTLY NO SIGMA / SUMMATION NOTATION ($\\sum$): Use standard words ('Sum of scores', 'Sum of degrees = 2e').
- STRICTLY NO EXTENSION 1 / 2 CONTENT: No mathematical induction, no vectors, no projectile motion, no complex numbers.
"""

    # 4. STAGE 6 MATHEMATICS EXTENSION 1 (Years 11-12)
    if is_stage6_extension1(year_level):
        if "11" in yl:
            return """
NSW NESA MATHEMATICS EXTENSION 1 YEAR 11 SYLLABUS (2024):
Generate only Year 11 content: further work with functions, polynomials,
further trigonometry (including three-dimensional trigonometry and compound
angle identities), permutations and combinations, and the binomial theorem.
Students also study the Year 11 Mathematics Advanced content.
Do not include the pigeonhole principle or discrete random variables.
Do not include Year 12 Extension 1 topics: mathematical induction, vectors,
inverse trigonometric functions, integration, differential equations,
binomial distributions, or sampling distributions.
"""
        return """
NSW NESA MATHEMATICS EXTENSION 1 YEAR 12 SYLLABUS (2024):
The content generated is for NSW Stage 6 Mathematics Extension 1 Year 12.
1. PERMITTED YEAR 12 EXTENSION 1 TOPICS:
- Proof: Mathematical Induction (sums, divisibility, inequalities).
- Vectors: 2D and 3D vectors (components, magnitude, direction, dot product, and 2D motion).
- Trigonometry: Inverse trigonometric functions ($\\arcsin x, \\arccos x, \\arctan x$), compound angle formulas, double angle formulas, $t$-formulas, auxiliary angle method $a\\cos x + b\\sin x = R\\cos(x-\\alpha)$.
- Calculus: Derivative of inverse trig functions, exponential, logarithmic, and trigonometric functions. Integration by simple algebraic substitution. Volumes of solids of revolution about $x$- and $y$-axes. Rates of change and differential equations ($\\frac{dy}{dt} = k(y-P)$).
- Polynomials: Polynomial division, Factor and Remainder theorems, roots of polynomials (relations between roots and coefficients for cubics and quartics).
- Combinatorics: Year 11 permutations and combinations, Pascal's triangle and binomial theorem expansions $(a+b)^n$ as prerequisites. Do not introduce the pigeonhole principle.
- Mechanics: Projectile motion (2D vectors without resistance).

2. STRICT NEGATIVE CONSTRAINTS (STRICTLY FORBIDDEN FOR EXTENSION 1):
- STRICTLY NO COMPLEX NUMBERS: Imaginary unit $i = \\sqrt{-1}$, Argand diagrams, modulus-argument form are strictly Extension 2.
- STRICTLY NO RESISTIVE MECHANICS: Motion with resistive forces or Simple Harmonic Motion (SHM) is strictly Extension 2.
- STRICTLY NO INTEGRATION BY PARTS OR PARTIAL FRACTIONS: Strictly Extension 2.
- STRICTLY NO UNIVERSITY / TERTIARY CONTENT (e.g. matrices, linear algebra, multivariable calculus $\\nabla$).
"""

    # 5. STAGE 6 MATHEMATICS EXTENSION 2 (Year 12)
    if is_stage6_extension2(year_level):
        return """
STRICT NSW NESA SYLLABUS BOUNDARY DIRECTIVE (STAGE 6 MATHEMATICS EXTENSION 2) - ZERO TOLERANCE LEAKAGE:
The content generated is strictly for NSW Stage 6 Mathematics Extension 2 (4-Unit).
1. PERMITTED EXTENSION 2 TOPICS:
- The Nature of Proof: Direct proof, proof by contradiction, contrapositive, counterexamples, mathematical induction (further inequalities and sequences).
- Complex Numbers: Arithmetic of complex numbers, Argand diagrams, modulus-argument form, polar form, Euler's formula $e^{i\\theta}$, roots of complex numbers, de Moivre's theorem, complex loci and regions, polynomials with complex coefficients.
- 3D Vectors: Coordinates in 3D, 3D vectors $\\mathbf{i}, \\mathbf{j}, \\mathbf{k}$, dot product, equations of lines and spheres in 3D, 3D vector geometry proofs.
- Integration: Integration by parts, partial fractions, trigonometric substitutions, recurrence relations for integrals.
- Mechanics: Simple Harmonic Motion (SHM), motion in a straight line with resistance (horizontal and vertical resistive motion).

2. STRICT NEGATIVE CONSTRAINTS (STRICTLY FORBIDDEN FOR EXTENSION 2):
- STRICTLY NO TERTIARY / UNIVERSITY ONLY MATHEMATICS:
  * NO multivariable calculus: partial derivatives $\\frac{\\partial f}{\\partial x}$, gradients $\\nabla$, double/triple integrals $\\iint$.
  * NO linear algebra: matrices, determinants, eigenvalues/eigenvectors.
  * NO epsilon-delta formal limit proofs.
  * NO abstract algebra (groups, rings, fields).
"""

    # 6. STAGE 6 MATHEMATICS ADVANCED (Years 11-12)
    # Default to Year 11 Advanced or Year 12 Advanced
    if "12" in yl and "adv" in yl:
        return """
STRICT NSW NESA SYLLABUS BOUNDARY DIRECTIVE (STAGE 6 YEAR 12 MATHEMATICS ADVANCED) - ZERO TOLERANCE LEAKAGE:
The requested resource is strictly for NSW Stage 6 Year 12 Mathematics Advanced (2-Unit).
1. PERMITTED YEAR 12 ADVANCED TOPICS:
- Differential Calculus: Product rule, quotient rule, chain rule, derivatives of $e^x, \\ln x, \\sin x, \\cos x, \\tan x$, second derivatives $f''(x)$, concavity, points of inflexion, optimization/maximum-minimum problems.
- Integral Calculus: Anti-differentiation, definite integrals, Fundamental Theorem of Calculus, area under a curve, area between two curves, trapezoidal rule.
- Financial Mathematics: Arithmetic sequences and series, geometric sequences and series, limiting sums, financial applications (annuities, investments, superannuation, reducing balance loans).
- Statistical Analysis: Discrete probability distributions, continuous random variables, probability density functions (PDFs), cumulative distribution functions (CDFs), expected value $E(X)$, variance $\\text{Var}(X)$, normal distribution (z-scores, empirical rule 68-95-99.7).

2. STRICT NEGATIVE CONSTRAINTS (FORBIDDEN OUT-OF-SYLLABUS TOPICS - ZERO TOLERANCE):
- STRICTLY NO EXTENSION 1 / EXTENSION 2 TOPICS:
  * NO Mathematical Induction.
  * NO 2D or 3D Vectors (no $\\mathbf{i}, \\mathbf{j}, \\mathbf{k}$, no dot product).
  * NO Projectile motion.
  * NO Combinatorics (permutations, combinations $nPr, nCr$, Binomial Theorem).
  * NO Inverse trigonometric functions ($\\arcsin, \\arccos, \\arctan$).
  * NO Polynomial division, Remainder Theorem, Factor Theorem for degree $\\ge 3$.
  * NO Integration by substitution, integration by parts, or volumes of solids of revolution.
  * NO Complex numbers or mechanics.
- STRICTLY NO STANDARD MATHEMATICS TOPICS:
  * NO Networks (vertices, edges, shortest paths, MSTs, CPA, max flow - strictly Standard).
- STRICTLY NO ABSOLUTE VALUE OF Y ($|y|$).
"""

    # Default: Year 11 Mathematics Advanced
    return """
STRICT NSW NESA SYLLABUS BOUNDARY & SCOPE DIRECTIVE FOR YEAR 11 MATHEMATICS ADVANCED (ZERO TOLERANCE LEAKAGE POLICY):
The requested resource is strictly and exclusively for NSW Stage 6 Year 11 Mathematics Advanced (2-Unit).
You must strictly restrict all explanations, definitions, formulas, problems, and questions to the Year 11 Mathematics Advanced syllabus and its Stage 5.3 prerequisites.
Under NO circumstances may you include, mention, or require any concepts from Year 12, Extension 1, Extension 2, Standard Mathematics, or Tertiary mathematics.

1. PERMITTED YEAR 11 ADVANCED SYLLABUS SCOPE & PREREQUISITES:
- Stage 5.3 Prerequisites: Surds (arithmetic, simplification, rationalising binomial denominators), index laws (negative & fractional indices), algebraic fractions, linear equations & inequalities, 2D coordinate geometry (distance, midpoint, gradient, line equations y=mx+c, ax+by+c=0, y-y_1=m(x-x_1), parallel/perpendicular lines, perpendicular distance formula, angle of inclination), right-angled & non-right-angled trigonometry (Sine Rule including ambiguous case, Cosine Rule, triangle area A = 1/2 ab sin C, bearings).
- Functions (MA-F1): Relations vs functions, vertical line test, function notation f(x), domain & range determination (algebraic & graphical), linear functions, direct & inverse variation (y = kx, y = k/x), quadratic functions (factoring, completing the square, vertex form, quadratic formula, discriminant Delta = b^2 - 4ac, quadratic inequalities), cubics (y = a(x-h)^3 + k and factored form), quartics in simple factored form, hyperbolas (y = k/(x-h) + c), circles & semi-circles, composite functions f(g(x)), piecewise-defined functions, absolute value y = |x| equations and inequalities, even and odd symmetry (f(-x) = f(x), f(-x) = -f(x)), transformations (translations, reflections, horizontal/vertical dilations).
- Trigonometric Functions (MA-T1, MA-T2): Angles of any magnitude, ASTC quadrant rules, exact values (0, pi/6, pi/4, pi/3, pi/2), radian measure, arc length (l = r theta), sector area (A = 1/2 r^2 theta), segment area (A = 1/2 r^2(theta - sin theta)), graphs of y = sin x, cos x, tan x with amplitude, period, vertical shift, and phase shift, reciprocal trigonometric ratios (sec x, cosec x, cot x), Pythagorean identities (sin^2 x + cos^2 x = 1, 1 + tan^2 x = sec^2 x, 1 + cot^2 x = csc^2 x), quotient identity (tan x = sin x / cos x), solving trigonometric equations within a domain in degrees or radians.
- Calculus - Introduction to Differentiation (MA-C1): Limits and continuity, average rate of change, gradient of secants vs tangents, differentiation from first principles (f'(x) = lim_{h->0} [f(x+h)-f(x)]/h), derivative of powers of x (d/dx(x^n) = n x^{n-1} for real n), linearity of differentiation (d/dx[af(x)+bg(x)] = af'(x)+bg'(x)), tangents and normals to polynomial curves at a point (y - y_1 = m(x - x_1)), differentiability vs non-differentiability.
- Exponential and Logarithmic Functions (MA-E1): Index laws, exponential graphs y = a^x, Euler's number e, natural exponential y = e^x, definition of logarithm (log_a x = y <=> a^y = x), natural logarithm ln x = log_e x, logarithm laws, change of base formula, solving exponential and logarithmic equations, exponential growth and decay models (N = N_0 e^{kt} or A = A_0 b^t).
- Statistical Analysis - Probability and Data (MAV-11-09/10): Sample spaces, outcomes, event probability, complementary events, Venn diagrams, two-way tables, tree diagrams (with/without replacement), mutually exclusive events, addition rule (P(A u B) = P(A) + P(B) - P(A n B)), independent events (P(A n B) = P(A) * P(B)), conditional probability (P(A|B) = P(A n B) / P(B)), univariate data summary statistics (mean, median, mode, range, IQR, standard deviation), parallel box plots, 1.5 x IQR outlier rule. Do not introduce discrete random variables or their probability distributions.

2. STRICT NEGATIVE CONSTRAINTS (FORBIDDEN OUT-OF-SYLLABUS TOPICS - ZERO TOLERANCE):
- STRICTLY NO YEAR 12 CALCULUS:
  * NO Integration / anti-derivatives / indefinite or definite integrals / integral sign.
  * NO Area under/between curves, or Trapezoidal Rule.
  * NO Product Rule, Quotient Rule, or Chain Rule (these are Year 12 MA-C2).
  * NO Derivatives of exponential functions (e^x), natural logs (ln x), or trigonometric functions (sin x, cos x, tan x).
  * NO Second derivatives (f''(x), d^2y/dx^2), concavity, or points of inflexion.
  * NO Optimization using calculus derivatives (only quadratic vertex optimization is in Year 11).
- STRICTLY NO YEAR 12 TOPICS:
  * NO Arithmetic Sequences/Series (T_n, S_n) or Geometric Sequences/Series (T_n, S_n, S_infinity).
  * NO Financial Mathematics: annuities, superannuation, future/present value, or reducing balance loans.
  * NO Continuous Random Variables, Probability Density Functions (PDFs), or Cumulative Distribution Functions (CDFs).
  * NO Normal Distribution, standard normal distribution, z-scores, or the 68-95-99.7 empirical rule.
  * NO Bivariate data analysis, scatter plots, Pearson's r, or regression lines.
  * NO Expected Value E(X) or Variance Var(X) of random variables (Year 12 MA-S2).
  * NO Discrete Random Variables or Discrete Probability Distributions (Year 12 MAV-12-07).
- STRICTLY NO EXTENSION 1 / EXTENSION 2 TOPICS:
  * NO Mathematical Induction.
  * NO Combinatorics, permutations, combinations (nPr, nCr), Binomial Theorem expansion, or Pigeonhole Principle.
  * NO Vectors (2D/3D vectors, dot products, vector projections).
  * NO Projectile motion or calculus kinematics.
  * NO Inverse trigonometric functions (arcsin, arccos, arctan, sin^{-1}, cos^{-1}, tan^{-1}).
  * NO Polynomial division, Remainder Theorem, Factor Theorem for degree >= 3, or sum/product of roots (Vieta's formulas).
  * NO Compound angle formulas (sin(A +- B)), double angle formulas (sin 2A, cos 2A), t-formulas, or auxiliary angles.
  * NO Circle geometry deductive Euclidean proofs.
  * NO Complex numbers or mechanics.
- STRICTLY NO ABSOLUTE VALUE OF Y (|y|):
  * Functions of the form y = |f(x)| are in scope, but relations involving |y| (such as |y| = f(x), |x| + |y| = c, or equations requiring solving for |y|) are strictly OUT OF SCOPE for NSW Mathematics Advanced. NEVER generate questions, examples, study notes, or exam hacks involving |y|.
- STRICTLY NO STANDARD MATHEMATICS TOPICS:
  * NO Networks, vertices, edges, Eulerian/Hamiltonian paths, Prim's or Kruskal's minimum spanning tree, or shortest paths.
  * NO Tax tables, PAYG income tax, Medicare levy, annual leave loading, or gross/net pay.
"""


# Stage-specific forbidden patterns for auditing content
STAGE4_FORBIDDEN_PATTERNS = [
    (r"\bquadratic\b|\bparabola\b|x\^2\s*[\+\-]\s*\d*x", "Stage 4 Quadratics/Parabolas"),
    (r"\bpythagor(?:as|ean)\b|a\^2\s*\+\s*b\^2\s*=\s*c\^2", "Stage 4 Pythagoras Theorem"),
    (r"\\sin\b|\\cos\b|\\tan\b|\btrigonometr(?:y|ic)\b|\bsoh\s*cah\s*toa\b|\bbearing(?:s)?\b", "Stage 4 Trigonometry"),
    (r"\bsurd(?:s)?\b|\\sqrt\{\d+\}", "Stage 4 Surds"),
    (r"\bsimultaneous equations\b", "Stage 4 Simultaneous Equations"),
    (r"\\frac\{dy\}\{dx\}|\\int\b|\bderivative\b|\bcalculus\b", "Stage 4 Calculus"),
    (r"\\sum\b|\\Sigma\b|∑", "Stage 4 Sigma Notation"),
]

STAGE5_FORBIDDEN_PATTERNS = [
    (r"\\frac\{dy\}\{dx\}|\\int\b|f'\s*\(|\bderivative\b|\bcalculus\b|\banti-?derivative\b|\blimit\b|\\lim\b", "Stage 5 Calculus"),
    (r"\bradian(?:s)?\b|\\pi\s*rad", "Stage 5 Radian Measure"),
    (r"\blogarithm(?:s)?\b|\\log\b|\\ln\b|\bexponential function e\b", "Stage 5 Logarithms"),
    (r"\\sum\b|\\Sigma\b|∑|\bsigma notation\b", "Stage 5 Sigma Notation"),
    (r"\barithmetic sequence\b|\bgeometric sequence\b|\barithmetic series\b|\bgeometric series\b", "Stage 5 Sequences/Series"),
    (r"\\mathbf\{[ij]\}|\\vec\{|\bvectors?\b", "Stage 5 Vectors"),
    (r"\bcomplex number\b|\bimaginary unit\b", "Stage 5 Complex Numbers"),
    (r"\|(?:\s*y\s*|\s*y\s*[\+\-][^|]*)\||\babs\s*\(\s*y\s*\)|\\lvert\s*y\s*\\rvert", "Stage 5 Absolute value of y"),
]

STAGE6_STANDARD_FORBIDDEN_PATTERNS = [
    (r"\\frac\{dy\}\{dx\}|\\int\b|f'\s*\(|\bderivative\b|\bcalculus\b|\bdifferentiate\b|\bintegrate\b|\blimit\b", "Standard Maths Calculus"),
    (r"\bradian(?:s)?\b|\\pi\s*rad", "Standard Maths Radian Measure"),
    (r"\\ln\b|\bnatural logarithm\b|e\^\{[a-z0-9]\}", "Standard Maths Natural Log/Exp"),
    (r"\bcontinuous random variable\b|\bprobability density function\b|\bcdf\b", "Standard Maths Continuous Random Variables"),
    (r"\\sum\b|\\Sigma\b|∑", "Standard Maths Sigma Notation"),
    (r"\bmathematical induction\b|\\mathbf\{[ij]\}|\bprojectile motion\b|\bcomplex number\b", "Standard Maths Ext 1/2 Content"),
]

STAGE6_EXT1_FORBIDDEN_PATTERNS = [
    (r"\bpigeonhole(?:\s+(?:principle|theorem))?\b", "Pigeonhole principle is outside the Extension 1 syllabus"),
    (r"\bcomplex number\b|\bargand diagram\b|\bimaginary unit\b|e\^\{i\\theta\}|\\text\{cis\}", "Extension 1 Complex Numbers (Ext 2 only)"),
    (r"\bresistive motion\b|\bresistance force\b|\bsimple harmonic motion\b|\bshm\b", "Extension 1 Mechanics with Resistance (Ext 2 only)"),
    (r"\bintegration by parts\b|\bpartial fractions\b", "Extension 1 Integration by Parts/Partial Fractions (Ext 2 only)"),
]

YEAR_11_EXT1_FORBIDDEN_PATTERNS = [
    (r"\bdiscrete random variables?\b|\bdiscrete probability distributions?\b", "Year 12 Advanced random variables"),
    (r"\bmathematical induction\b|\bproof by induction\b", "Year 12 Extension 1 induction"),
    (r"\b(?:2d|3d|two-dimensional|three-dimensional) vectors?\b|\\mathbf\{[ijk]\}", "Year 12 Extension 1 vectors"),
    (r"\binverse trigonometric functions?\b|\\arcsin|\\arccos|\\arctan", "Year 12 Extension 1 inverse trigonometry"),
    (r"\\int\b|\bintegrat(?:e|ion)\b|\bdifferential equations?\b", "Year 12 Extension 1 calculus"),
    (r"\bbinomial distributions?\b|\bsampling distributions?\b", "Year 12 Extension 1 statistics"),
]

YEAR_11_ADV_FORBIDDEN_PATTERNS = [
    # Absolute value of y
    (r"\|(?:\s*y\s*|\s*y\s*[\+\-][^|]*)\||\babs\s*\(\s*y\s*\)|\\lvert\s*y\s*\\rvert|\\vert\s*y\s*\\vert|\babsolute value of y\b", "Absolute value of y (|y|) not in Stage 6 syllabus"),
    # Year 12 Calculus
    (r"\\int\b|\\int_|\bintegral\b|\bintegrals\b|\bintegrate\b|\banti-?derivative\b|\btrapezoidal rule\b", "Year 12 Integral Calculus"),
    (r"\bproduct rule\b|\bquotient rule\b|\bchain rule\b", "Year 12 Differentiation Rules (Product/Quotient/Chain)"),
    (r"\\frac\{d\}\{dx\}\s*e\^|\\frac\{d\}\{dx\}\s*\\ln|\\frac\{d\}\{dx\}\s*\\sin|\\frac\{d\}\{dx\}\s*\\cos|\\frac\{d\}\{dx\}\s*\\tan", "Year 12 Exp/Log/Trig Derivatives"),
    (r"f''\s*\(|\\frac\{d\^2y\}\{dx\^2\}|\bconcavity\b|\bpoints? of inflexion\b|\bpoint of inflection\b", "Year 12 Second Derivatives & Concavity"),
    # Year 12 Series, Finance, Stats
    (r"\barithmetic sequence\b|\bgeometric sequence\b|\barithmetic series\b|\bgeometric series\b|\blimiting sum\b", "Year 12 Sequences and Series"),
    (r"\bannuit(?:y|ies)\b|\bsuperannuation\b|\bpresent value\b|\bfuture value\b|\breducing balance\b", "Year 12 Financial Mathematics"),
    (r"\b(?:discrete|continuous) random variables?\b|\b(?:discrete )?probability distributions?\b|\bprobability density function\b|\bcdf\b", "Year 12 Random Variables"),
    (r"\bnormal distribution\b|\bz-score\b|\bstandard normal\b|68-95-99\.7", "Year 12 Normal Distribution"),
    (r"\bbivariate data\b|\bpearson(?:'s)?\b|\bcorrelation coefficient\b|\bregression line\b|\bresidual plot\b", "Year 12 Bivariate Data"),
    (r"\bexpected value\b|\be\(x\)\s*=|\bvar\(x\)\s*=", "Year 12 Random Variable Expectation/Variance"),
    # Extension 1 & 2
    (r"\bmathematical induction\b|\binductive step\b|\bbase step\b", "Extension 1 Mathematical Induction"),
    (r"\bpermutation\b|\bcombination\b|\bcombinatorics\b|\bpigeonhole\b|\\binom|\b\^nC_r\b|\bnCr\b|\bnPr\b", "Extension 1 Combinatorics & Binomial Theorem"),
    (r"\\mathbf\{[ij]\}|\\vec\{|\bdot product\b|\bvector projection\b|\bscalar product\b", "Extension 1 Vectors"),
    (r"\bprojectile motion\b|\blaunch velocity\b", "Extension 1 Projectile Motion"),
    (r"\\arcsin|\\arccos|\\arctan|\\sin\^\{-1\}|\\cos\^\{-1\}|\\tan\^\{-1\}|\barcsin\b|\barccos\b|\barctan\b", "Extension 1 Inverse Trigonometric Functions"),
    (r"\bpolynomial division\b|\bremainder theorem\b|\bfactor theorem\b|\bvieta\b|\bsum and product of roots\b", "Extension 1 Polynomials Division/Theorems"),
    (r"\bcompound angle\b|\bdouble angle\b|\\sin\(A\s*[+-]|\\cos\(A\s*[+-]|\bt-formula\b|\bauxiliary angle\b", "Extension 1 Compound/Double Angle Trig"),
    (r"\bcyclic quad|\balternate segment theorem\b|\bcircle geometry proof\b", "Extension 1 Circle Geometry Proofs"),
    (r"\bcomplex number\b|\bargand diagram\b|\bimaginary unit\b", "Extension 2 Complex Numbers"),
    # Standard Maths
    (r"\beulerian\b|\bhamiltonian\b|\bprim's algorithm\b|\bkruskal's algorithm\b|\bminimum spanning tree\b|\bshortest path\b|\bnetwork diagram\b", "Standard Mathematics Networks"),
    (r"\bmedicare levy\b|\bpayg\b|\btaxable income\b|\bannual leave loading\b", "Standard Mathematics Financial/Tax"),
]


def audit_nsw_syllabus_violations(data: Any, year_level: str) -> List[str]:
    """
    Scans generated data structure for any out-of-syllabus terms or concepts
    violating the NSW Mathematics Syllabus boundaries for the specified year level/stage.
    """
    patterns_to_check: List[Tuple[str, str]] = []
    if is_stage4(year_level):
        patterns_to_check = STAGE4_FORBIDDEN_PATTERNS
    elif is_stage5(year_level):
        patterns_to_check = STAGE5_FORBIDDEN_PATTERNS
    elif is_stage6_standard(year_level):
        patterns_to_check = STAGE6_STANDARD_FORBIDDEN_PATTERNS
    elif is_stage6_extension1(year_level):
        patterns_to_check = list(STAGE6_EXT1_FORBIDDEN_PATTERNS)
        if "11" in str(year_level):
            patterns_to_check += YEAR_11_EXT1_FORBIDDEN_PATTERNS
    elif is_year_11_advanced(year_level):
        patterns_to_check = YEAR_11_ADV_FORBIDDEN_PATTERNS

    if not patterns_to_check:
        return []

    collected_texts = []

    def _extract_text(obj: Any):
        if isinstance(obj, str):
            collected_texts.append(obj)
        elif isinstance(obj, dict):
            for key, v in obj.items():
                if key in {"custom_instructions", "extra_instructions", "_syllabus_audit"}:
                    continue
                _extract_text(v)
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                _extract_text(item)

    _extract_text(data)
    full_text = " ".join(collected_texts).lower()

    violations = []
    for pattern, description in patterns_to_check:
        match = re.search(pattern, full_text, flags=re.IGNORECASE)
        if match:
            violations.append(f"{description} (matched: '{match.group(0)}')")

    return violations


def audit_year11_advanced_violations(data: Any, year_level: str) -> List[str]:
    """Backwards-compatible alias for audit_nsw_syllabus_violations."""
    return audit_nsw_syllabus_violations(data, year_level)


def audit_and_sanitize_year11_advanced_data(data: Dict[str, Any], year_level: str, strict: bool = False) -> Dict[str, Any]:
    """
    Validates and logs any syllabus boundary anomalies across all stages.
    Attaches an audit flag to the dictionary for verification.
    """
    if not isinstance(data, dict):
        return data

    violations = audit_nsw_syllabus_violations(data, year_level)
    if violations:
        logger.warning(
            f"[Syllabus Boundary Alert] {year_level} resource contains potential out-of-scope content: {violations}"
        )
        data["_syllabus_audit"] = {
            "status": "warning",
            "year_level": year_level,
            "violations_flagged": violations
        }
        if strict and (is_year_11_advanced(year_level) or (is_stage6_extension1(year_level) and "11" in str(year_level))):
            raise ValueError(
                f"Generated {year_level} content crossed the NSW 2024 syllabus boundary: "
                + "; ".join(violations)
            )
    else:
        data["_syllabus_audit"] = {
            "status": "passed",
            "year_level": year_level,
            "boundary": f"Pure NSW Syllabus Alignment ({year_level})"
        }

    return data


def suggest_subtopics_ai(year_level: str, topic: str, api_key: Optional[str] = None, textbook: str = "CambridgeMATHS NSW") -> List[str]:
    """Uses Gemini to generate 4 to 6 Australian curriculum subtopics for any topic and textbook."""
    client = get_client(api_key)
    boundary_prompt = get_stage6_syllabus_boundary_prompt(year_level, topic)
    prompt = f"""You are a Lead Mathematics Curriculum Specialist in Australia following the NSW NESA syllabus and the {textbook} textbook series.
List 4 to 6 core curriculum subtopics/chapters for {year_level} on the topic "{topic}".
{boundary_prompt}
Respond with valid JSON ONLY:
{{
  "subtopics": [
    "Subtopic 1",
    "Subtopic 2",
    "Subtopic 3",
    "Subtopic 4",
    "Subtopic 5"
  ]
}}
"""
    try:
        config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=config
        )
        data = clean_json_response(response.text)
        suggested = data.get("subtopics", get_curriculum_subtopics(year_level, topic, textbook=textbook))
        return [sub for sub in suggested if is_syllabus_topic_allowed(year_level, sub)]
    except Exception:
        return get_curriculum_subtopics(year_level, topic, textbook=textbook)

def get_api_key(provided_key: Optional[str] = None) -> Optional[str]:
    """
    Returns the provided key if given, or reads from environment / .env file only if provided_key is None.
    If provided_key is explicitly passed as an empty string (""), returns "" so that unauthenticated
    or non-configured users do not silently piggyback on the center's master environment key.
    """
    if provided_key is not None:
        return provided_key.strip()
    return os.environ.get("GEMINI_API_KEY", "").strip()

def get_client(api_key: Optional[str] = None):
    if not HAS_GENAI:
        raise ImportError("google-genai library is not installed. Please install it with pip install google-genai")
    key = get_api_key(api_key)
    if not key:
        raise ValueError("Google Gemini API Key is missing. Please configure your personal Gemini API key in the sidebar.")
    return genai.Client(api_key=key)

def repair_json_latex_escapes(raw_text: str) -> str:
    r"""
    Repairs unescaped LaTeX backslashes inside JSON string literals produced by LLMs.
    In standard JSON, only \" \\ / \b \f \n \r \t and \uXXXX are valid escape sequences.
    LLMs generating mathematical content often output single backslashes in \sqrt, \frac,
    \mathbf, \theta, \times, \Delta, \vec, \alpha, etc., which cause JSONDecodeError: Invalid \escape.
    This scanner safely escapes raw backslashes without corrupting existing valid escapes.
    """
    result = []
    i = 0
    n = len(raw_text)
    in_string = False

    while i < n:
        c = raw_text[i]

        # Check for quote toggling in_string
        if c == '"':
            # Count preceding backslashes
            bs_count = 0
            k = i - 1
            while k >= 0 and raw_text[k] == '\\':
                bs_count += 1
                k -= 1
            if bs_count % 2 == 0:
                in_string = not in_string
            result.append(c)
            i += 1
            continue

        if in_string and c == '\\':
            if i + 1 < n:
                next_c = raw_text[i + 1]
                # Already double backslash: \\
                if next_c == '\\':
                    result.append('\\\\')
                    i += 2
                    continue
                # Escaped quote: \"
                elif next_c == '"':
                    result.append('\\"')
                    i += 2
                    continue
                # Valid JSON escape: \/
                elif next_c == '/':
                    result.append('\\/')
                    i += 2
                    continue
                # Valid unicode escape: \uXXXX
                elif next_c == 'u' and i + 5 < n and all(raw_text[i + 2 + j] in "0123456789abcdefABCDEF" for j in range(4)):
                    result.append(raw_text[i:i + 6])
                    i += 6
                    continue
                # Check for b, f, n, r, t:
                # If followed by another letter, it's virtually always a LaTeX command:
                # e.g. \frac, \forall, \theta, \times, \tan, \text, \right, \rho, \beta, \binom, \begin, \bar, \neq, \nabla, \not
                elif next_c in "bfnrt" and (i + 2 < n and raw_text[i + 2].isalpha()):
                    result.append('\\\\')
                    result.append(next_c)
                    i += 2
                    continue
                # Standard whitespace escapes: \n, \r, \t, \b, \f when NOT followed by letters
                elif next_c in "bfnrt":
                    result.append('\\' + next_c)
                    i += 2
                    continue
                else:
                    # Invalid JSON escape: \s (\sqrt), \m (\mathbf), \c (\cos), \a (\alpha), \{, \$, etc.
                    # Escape the backslash so JSON receives \\ + next_c
                    result.append('\\\\')
                    result.append(next_c)
                    i += 2
                    continue
            else:
                # Trailing backslash
                result.append('\\\\')
                i += 1
                continue

        result.append(c)
        i += 1

    cleaned = "".join(result)
    # Remove trailing commas before } or ]
    cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
    return cleaned


def clean_json_response(raw_text: str) -> Dict[str, Any]:
    """Extracts and parses JSON even if wrapped in markdown fences or containing unescaped LaTeX math backslashes."""
    from pdf_generator import enforce_australian_english_dict

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    parsed = None
    # 1. Try standard JSON parse first
    try:
        parsed = json.loads(cleaned, strict=False)
    except Exception:
        pass

    # 2. Try repairing unescaped LaTeX backslashes & trailing commas
    if parsed is None:
        try:
            repaired = repair_json_latex_escapes(cleaned)
            parsed = json.loads(repaired, strict=False)
        except Exception:
            pass

    # 3. Try finding outermost JSON object { ... } and repairing that
    if parsed is None:
        match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if match:
            try:
                repaired = repair_json_latex_escapes(match.group(1))
                parsed = json.loads(repaired, strict=False)
            except Exception:
                pass

    # 4. Final attempt: re-raise original or repaired error
    if parsed is None:
        repaired = repair_json_latex_escapes(cleaned)
        parsed = json.loads(repaired, strict=False)

    return enforce_australian_english_dict(parsed)

# --- 1. WORKSHEET & AUTO-KEY GENERATION (SUBTOPIC & DIFFICULTY-ALLOCATED) ---
def generate_curriculum_worksheet(
    topic: str,
    year_level: str,
    subtopics_dict: Union[Dict[str, int], Dict[str, Dict[str, int]]],
    difficulty: str = "Medium",
    sheet_type: str = "Homework",
    term: Optional[int] = None,
    week: Optional[int] = None,
    custom_instructions: str = "",
    textbook: str = "CambridgeMATHS NSW",
    api_key: Optional[str] = None,
    num_mc: int = 0,
    use_search: bool = False,
    theory_reference_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generates an authentic Australian exam worksheet with flexible mark allocations,
    Multiple Choice sections, subtopic/difficulty allocations based on NSW syllabus textbooks,
    TikZ & Matplotlib diagrams, and full LaTeX math.
    """
    client = get_client(api_key)

    # Build pedagogical alignment context from Theory Booklet if provided
    theory_alignment_text = ""
    if theory_reference_data and isinstance(theory_reference_data, dict):
        tb_concepts = theory_reference_data.get("concepts", [])
        tb_lines = []
        for c in tb_concepts:
            c_name = c.get("concept_name", "")
            ex_stems = [ex.get("problem_text", "") for ex in c.get("teacher_examples", [])[:2] if ex.get("problem_text")]
            pq_stems = [pq.get("text", "") for pq in c.get("practice_questions", [])[:3] if pq.get("text")]
            if c_name:
                tb_lines.append(f"- Concept: {c_name}")
            if ex_stems:
                tb_lines.append(f"  * Worked Example Prototypes: {' | '.join(ex_stems)}")
            if pq_stems:
                tb_lines.append(f"  * Class Practice Prototypes: {' | '.join(pq_stems)}")
        if tb_lines:
            theory_alignment_text = f"""
PEDAGOGICAL PARALLELISM TO THEORY BOOKLET (CRITICAL REQUIREMENT):
The students have just studied this topic in class using their Theory Booklet.
Every single question in this {sheet_type} booklet MUST be a direct pedagogical parallel / twin variant to the concepts, worked demonstration examples, and practice questions from the Theory Booklet:
{chr(10).join(tb_lines)}

STRICT PARALLEL QUESTION RULES:
1. Mirror the exact question phrasing, algebraic methods, and problem structures from the Theory Booklet (e.g. testing whether relations are functions via VLT, finding domain & range of root/rational functions, finding perpendicular/parallel line equations, collinearity using gradients).
2. Vary the numerical coefficients, signs, and constants so the numbers are fresh, but the mathematical strategy required is identical to what the student saw in their Theory Booklet.
3. DO NOT introduce unfamiliar problem types, obscure relations, or unintroduced tricks. Students must be able to open their Theory Booklet and immediately recognize how to solve each question!
"""
    elif sheet_type in ["Homework", "In-Class"]:
        theory_alignment_text = f"""
PEDAGOGICAL PARALLELISM TO CLASSROOM THEORY (CRITICAL):
This {sheet_type} booklet must contain questions that directly mirror standard classroom theory examples and exercises. Each question should follow standard NSW textbook templates (finding domains/ranges, linear equations and intercepts, perpendicularity conditions, vertical line test) with clean numbers, so students can practice what they were taught in class without confusing jumps in abstraction.
"""

    # Check if nested difficulty dict format is provided: {subtopic: {"Easy": 1, "Medium": 2, ...}}
    is_detailed_allocation = any(isinstance(v, dict) for v in subtopics_dict.values())

    if is_detailed_allocation:
        total_requested_items = sum(
            sum(counts.values()) if isinstance(counts, dict) else int(counts)
            for counts in subtopics_dict.values()
        )
        if total_requested_items <= 0:
            total_requested_items = 10
            subtopics_dict = {topic: {"Easy": 3, "Medium": 4, "Hard": 2, "Extremely Hard": 1}}

        allocation_lines = []
        diff_totals = {"Easy": 0, "Medium": 0, "Hard": 0, "Extremely Hard": 0, "Past Exam": 0}
        for sub, counts in subtopics_dict.items():
            if isinstance(counts, dict):
                sub_total = sum(counts.values())
                if sub_total > 0:
                    breakdown_parts = []
                    for lvl in ["Easy", "Medium", "Hard", "Extremely Hard", "Past Exam"]:
                        c = counts.get(lvl, 0)
                        if c > 0:
                            breakdown_parts.append(f"{c} {lvl}")
                            diff_totals[lvl] = diff_totals.get(lvl, 0) + c
                    allocation_lines.append(f"- Subtopic '{sub}' (Total: {sub_total} items): {', '.join(breakdown_parts)}")
            else:
                if counts > 0:
                    allocation_lines.append(f"- Subtopic '{sub}': generate exactly {counts} items")
        subtopic_allocation_text = "\n".join(allocation_lines)
        active_diffs = [f"{diff_totals[l]} {l}" for l in ["Easy", "Medium", "Hard", "Extremely Hard", "Past Exam"] if diff_totals.get(l, 0) > 0]
        if active_diffs:
            difficulty = f"Mixed ({', '.join(active_diffs)})"
    else:
        total_requested_items = sum(subtopics_dict.values())
        if total_requested_items <= 0:
            total_requested_items = 10
            subtopics_dict = {topic: 10}

        subtopic_allocation_text = "\n".join([
            f"- Subtopic '{sub}': generate exactly {count} item{'s' if count > 1 else ''}"
            for sub, count in subtopics_dict.items() if count > 0
        ])

    mc_prompt_section = ""
    if num_mc > 0:
        mc_prompt_section = f"""
MULTIPLE CHOICE SECTION (SECTION 1 - MANDATORY):
- Generate exactly {num_mc} Multiple Choice questions at the beginning as Section 1.
- Each Multiple Choice question MUST include "type": "multiple_choice" and an "options" object:
  "options": {{"A": "Choice A...", "B": "Choice B...", "C": "Choice C...", "D": "Choice D..."}}
- In "text", place ONLY the question statement/equation. Do NOT embed (A)/(B)/(C)/(D) options in "text".
- Heavily randomize correct answer options across A, B, C, D (do not always pick 'A').
- In "correct_answer", specify "(C) $x = 4$".
- Mark for each Multiple Choice item MUST be 1.
- Place the remaining {total_requested_items} items as Section 2 (Free-Response questions).
"""

    prompt = f"""You are a Lead Mathematics Curriculum Specialist for DA Tuition in Australia, using the {textbook} Stage 4/5/6 NSW syllabus textbooks.
Generate a high-quality Australian curriculum math worksheet for {year_level}.

SPECIFICATIONS:
- Year Level: {year_level}
- Main Topic: {topic}
- Textbook Reference: {textbook}
- Worksheet Type: {sheet_type}{f' (Term {term} Week {week})' if term and week else ''}
- Difficulty Level: {difficulty} (Options: Easy, Medium, Hard, Extremely Hard, Past Exam)
- Total Items: {total_requested_items + num_mc}
{f'- Special Tutor Instructions: {custom_instructions}' if custom_instructions else ''}

{mc_prompt_section}
{theory_alignment_text}
EXACT SUBTOPIC & DIFFICULTY QUESTION ALLOCATIONS:
{subtopic_allocation_text}

DIFFICULTY LEVEL CRITERIA (MANDATORY):
- Easy (Commit to Memory): Foundational definitions, single-step substitution, direct formula evaluation, or simple recall (typically 1 mark).
- Medium (Further Practice): Standard textbook exercises, routine 2-step calculations, basic algebraic rearrangement, or standard geometric problem (typically 1 to 2 marks).
- Hard (Application): Multi-step non-routine problem solving, reverse calculations (working backwards), combining multiple concepts, proofs, or unfamiliar contexts (typically 2 to 3 marks).
- Extremely Hard (Thinking Creatively): Extension/Challenging exam question, multi-part synthesis, rigorous formal proof, complex geometric reasoning, or Olympiad/HSC Extension style problems (typically 3 to 4 marks).
- Past Exam (Exam Questions): Authentic NSW Stage 6 (or Stage 4/5) Trial and HSC examination question style, inspired by past exams from premier selective and independent schools (e.g. James Ruse Agricultural High, Baulkham Hills, Sydney Boys, Sydney Girls, North Sydney Boys, North Sydney Girls, Sydney Grammar, Barker College, Knox Grammar, as archived on THSC Online: https://thsconline.github.io/s/). Must feature authentic examination phrasing, multi-part synthesis (e.g. (a), (b)(i), (b)(ii)), rigorous marking rubrics, non-routine mathematical deduction, and deep conceptual depth (typically 3 to 5 marks).

For every single question, you MUST set the "difficulty" attribute to the exact requested level: "Easy", "Medium", "Hard", "Extremely Hard", or "Past Exam" matching the allocations above.

{get_stage6_syllabus_boundary_prompt(year_level, topic)}
FLEXIBLE MARK ALLOCATION:
1. You are allowed to allocate marks (e.g. 1 mark, 2 marks, 3 marks, or 4 marks) according to the complexity, depth, and steps required for each question.
   - 1 mark for straightforward 1-step calculations, definitions, or direct evaluations.
   - 2 marks for standard multi-step calculations, geometric applications, or algebraic solving.
   - 3 to 4 marks for comprehensive derivations, multi-part proofs, or complex multi-stage problems.
2. Label each question or subpart clearly: e.g. "1", "2", "3", or "1(a)", "1(b)", "2(a)", "2(b)", etc.
3. In the worked solutions, indicate where each mark is awarded (e.g. "[1 mark for finding the vector, 1 mark for calculating magnitude]").

DIAGRAMS & PYTHON GRAPHING (MANDATORY WHERE APPROPRIATE):
- LANGUAGE REQUIREMENT: STRICT AUSTRALIAN ENGLISH SPELLING throughout (e.g. 'factorise', 'rationalise', 'centre', 'metres', 'labelled', 'modelling', 'colour', 'behaviour', 'minimise', 'maximise', 'summarise'). NEVER use US spellings.
- MANDATORY QUESTION VARIETY: BALANCED MIX OF DIAGRAM & NON-DIAGRAM QUESTIONS:
  * For visual, geometric, network, graph, trigonometry, coordinate geometry, or measurement topics:
    - Approximately 40% to 60% of questions MUST include given visual diagrams in `diagram_tikz`.
    - The remaining ~40% to 60% of questions MUST be non-diagram algebraic drills or direct calculations (`diagram_tikz: ""`).
    - NEVER produce a worksheet where 100% of questions lack diagrams! Ensure realistic variety!
- MANDATORY GIVEN DIAGRAMS FOR STUDENTS (HSC / NSW EXAM STANDARD):
  * Students must always be GIVEN diagrams for questions involving networks, graph theory, shortest paths, minimum spanning trees, geometry, bearings, angles of elevation/depression, or trigonometry, unless the question explicitly awards marks for constructing/drawing the diagram itself.
  * NEVER describe network vertices and edge weights or geometric configurations solely in text without providing the compilable LaTeX TikZ diagram in `diagram_tikz`. In NSW examinations, students are supplied with the visual diagram.
- For questions involving geometry, 2D/3D vectors, angles, geometric proofs, triangles, circles, networks/graphs, probability trees, Venn diagrams, coordinate geometry, or calculus curves: you MUST provide a compilable LaTeX TikZ diagram in the "diagram_tikz" field (or embedded in "text").
- MANDATORY GRAPH SKETCHING IN SOLUTIONS: Whenever a question asks to "sketch", "plot", "draw the graph", or "graph" a function, relation, or curve: provide a complete, beautifully labelled TikZ coordinate plane in "solution_diagram_tikz" with axes, origin, curve, and key features.
- For worked solutions requiring geometric construction, angle markings, vector additions, sign diagrams, or step-by-step visual proofs: provide a compilable TikZ diagram in the "solution_diagram_tikz" field.
- DIAGRAM SPACING RULES (CRITICAL):
  * For number lines and probability lines, use a generous horizontal axis (e.g. 10cm to 12cm width) and stagger label heights (or place alternating labels above and below the axis) so coordinates and text NEVER collide or overlap.
  * For Venn diagrams, ensure circles have adequate radius and distinct centres with clear label positioning inside each region.
  * All TikZ code must be clean, 100% syntactically valid LaTeX enclosed in \\begin{{center}}\\begin{{tikzpicture}}...\\end{{tikzpicture}}\\end{{center}}.
- For Cartesian coordinate geometry, graphing functions (parabolas, hyperbolas, cubics, exponentials, circles), slope fields, or normal distributions, you may output a Python Matplotlib graph block in the "text" field:
GRAPH_START
type: function
expr: x**2 - 4*x + 3
xmin: -1
xmax: 5
xlabel: x
ylabel: y
GRAPH_END
Or for normal distributions:
GRAPH_START
type: normal
mean: 100
std: 15
shade_min: 85
shade_max: 115
xlabel: Score
ylabel: Density
GRAPH_END

LATEX MATHEMATICAL FORMATTING (MANDATORY):
Every variable, formula, fraction, equation, power, or root MUST be enclosed in single dollar signs $...$ (e.g. '$6x^2 - 11x - 10 = 0$', '$P(A \\mid B) = \\frac{{3}}{{5}}$', '$x = \\frac{{-4 \\pm \\sqrt{{26}}}}{{2}}$', '$\\mathbf{{v}} = 2\\mathbf{{i}} - 3\\mathbf{{j}} + 6\\mathbf{{k}}$').

CRITICAL JSON ESCAPING:
Inside JSON string values, escape every LaTeX backslash as double backslash (e.g. write '\\\\frac' instead of '\\frac', '\\\\sqrt' instead of '\\sqrt', and '\\\\mathbf' instead of '\\mathbf'). Return strictly valid JSON.

OUTPUT FORMAT:
Respond with valid JSON ONLY matching this structure:
{{
  "title": "{year_level} Mathematics - {topic} {sheet_type}",
  "topic": "{topic}",
  "year_level": "{year_level}",
  "term": {term if term is not None else "null"},
  "week": {week if week is not None else "null"},
  "sheet_type": "{sheet_type}",
  "total_items": {total_requested_items + num_mc},
  "questions": [
    {{
      "item_label": "1",
      "text": "Algebraic calculation or direct formula question (no diagram needed)...",
      "diagram_tikz": "",
      "solution_diagram_tikz": "",
      "marks": 1,
      "difficulty": "Easy",
      "subtopic": "Subtopic Name",
      "type": "multiple_choice",
      "options": {{
        "A": "Option A...",
        "B": "Option B...",
        "C": "Option C...",
        "D": "Option D..."
      }},
      "solution_steps": "Explanation of why C is correct...",
      "correct_answer": "(C) Option C..."
    }},
    {{
      "item_label": "2",
      "text": "In the diagram shown below, find the value of ... (visual deduction question)",
      "diagram_tikz": "\\\\begin{{center}}\\\\begin{{tikzpicture}}...\\\\end{{tikzpicture}}\\\\end{{center}}",
      "solution_diagram_tikz": "",
      "marks": 2,
      "difficulty": "Medium",
      "subtopic": "Subtopic Name",
      "type": "short_answer",
      "solution_steps": "Step-by-step working using the given diagram...",
      "correct_answer": "$x = 5$"
    }}
  ],
  "marking_key": {{
    "1": "C",
    "2": "$x = 5$"
  }}
}}
"""

    models_to_try = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
    last_err = None

    for model_name in models_to_try:
        try:
            tools = [types.Tool(google_search=types.GoogleSearch())] if use_search else None
            config = types.GenerateContentConfig(
                response_mime_type="application/json" if not use_search else None,
                temperature=0.2,
                max_output_tokens=65536,
                tools=tools
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            data = clean_json_response(response.text)
            data["title"] = f"{year_level} Mathematics - {topic} {sheet_type}"
            data["topic"] = topic
            data["year_level"] = year_level
            data["term"] = term
            data["week"] = week
            data["sheet_type"] = sheet_type
            data["total_marks"] = sum(int(q.get("marks", 1)) for q in data.get("questions", []))
            data["custom_instructions"] = custom_instructions or ""
            data["extra_instructions"] = custom_instructions or ""
            for q in data.get("questions", []):
                if "difficulty" not in q:
                    q["difficulty"] = difficulty

            # Token and cost tracking (Gemini Flash rates)
            prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            candidates_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            est_cost = estimate_gemini_cost(prompt_tokens, candidates_tokens, model=model_name)
            data["meta_tokens"] = total_tokens
            data["meta_cost"] = round(est_cost, 5)
            from pdf_generator import order_and_renumber_worksheet_questions
            data["questions"] = order_and_renumber_worksheet_questions(data.get("questions", []))
            m_key = {}
            for q in data["questions"]:
                lbl = str(q.get("item_label") or q.get("num") or "").strip()
                if lbl:
                    m_key[lbl] = str(q.get("correct_answer") or q.get("final_answer") or "").strip()
            data["marking_key"] = m_key

            return audit_and_sanitize_year11_advanced_data(data, year_level, strict=True)
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Worksheet generation failed: {last_err}")

# --- 2. 1-CLICK AI HOMEWORK MARKING ---
def grade_student_submission(
    student_pdf_bytes: bytes,
    marking_key: Dict[str, Any],
    total_marks: float,
    worksheet_title: str = "",
    term: int = 1,
    week: int = 1,
    api_key: Optional[str] = None,
    questions_metadata: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Grades a handwritten student homework PDF against the marking key using Gemini 3.7 Flash.
    Supports question metadata to tag mistakes directly with concept_name and cognitive_level.
    """
    client = get_client(api_key)
    key_formatted = json.dumps(marking_key, indent=2)

    meta_prompt_section = ""
    if questions_metadata:
        meta_lines = []
        for qm in questions_metadata:
            lbl = str(qm.get("item_label") or qm.get("num") or "").strip()
            c_name = qm.get("concept_name") or qm.get("subtopic") or ""
            c_lvl = qm.get("cognitive_level") or qm.get("difficulty") or ""
            if lbl and (c_name or c_lvl):
                meta_lines.append(f"   - Question {lbl}: Concept = '{c_name}', Cognitive Level = '{c_lvl}'")
        if meta_lines:
            meta_prompt_section = "\nQUESTION CONCEPT & COGNITIVE LEVEL MAPPING:\n" + "\n".join(meta_lines) + "\n"

    prompt = f"""You are a Senior Math Examiner for DA Tuition. Grade the attached handwritten student homework PDF against the Official Marking Key.

OFFICIAL MARKING KEY (EVERY ITEM IS STRICTLY 1 MARK):
{key_formatted}

TOTAL MARKS: {total_marks}
HEADER CONTEXT: Term {term} Week {week} Homework ({worksheet_title})
{meta_prompt_section}
    EVALUATION RULES:
1. NAME EXTRACTION: Extract student First and Last Name from top of paper.
2. ACCURATE SCORING & PARTIAL MARKS:
   - Each answer box corresponds to a question/subpart label (e.g. '1(a)', '1(b)', '2').
   - Compare student final answer against the marking key.
   - Award full marks if correct.
   - If a question is worth multiple marks and the student shows correct partial working or has a minor arithmetic slip, award partial marks (e.g. 1/2 or 2/3).
   - If incorrect or left blank, mark as "Incorrect" or "Missing" and deduct the appropriate marks lost.
3. SCORING TOTALS:
   - Total Score = sum of marks earned across all questions (can be fractional if partial credit was given).
   - Accuracy Percentage = round((Total Score / {total_marks}) * 100).
4. DIAGNOSTIC TAGGING:
   - For every mistake or lost mark, tag the topic, subtopic, concept_name, cognitive_level, marks lost, and diagnostic error type.
5. CORRECTION COMPLETENESS:
   - The `mistakes` list is mandatory whenever score is below total marks.
   - Include one row for every question that lost marks, including blank or unanswered questions.
   - Never return an empty `mistakes` list when any marks were lost.

OUTPUT FORMAT:
Respond with valid JSON ONLY:
{{
  "extracted_name": "Student Name",
  "header": "Term {term} Week {week} Homework Report",
  "score": 18.0,
  "total_marks": {total_marks},
  "accuracy_pct": 90.0,
  "mistakes": [
    {{
      "question_num": "1(a)",
      "topic": "Probability",
      "subtopic": "Conditional Probability",
      "concept_name": "Concept 2: Conditional Probability",
      "cognitive_level": "Level 2 - Exam Application",
      "status": "Incorrect",
      "marks_lost": 1.0,
      "student_answer": "3/10",
      "correct_answer": "3/5",
      "error_type": "Calculation Error",
      "details": "Divided by P(A) instead of P(B)."
    }}
  ],
  "summary_text": "Encouraging 2-3 sentence tutor summary explaining strengths and concepts to review."
}}
"""

    models_to_try = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
    last_err = None

    pdf_part = types.Part.from_bytes(data=student_pdf_bytes, mime_type="application/pdf")

    # Build fallback question metadata lookup
    qm_lookup = {}
    if questions_metadata:
        for qm in questions_metadata:
            lbl = str(qm.get("item_label") or qm.get("num") or "").strip()
            if lbl:
                qm_lookup[lbl] = qm

    for model_name in models_to_try:
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
            response = client.models.generate_content(
                model=model_name,
                contents=[pdf_part, prompt],
                config=config
            )
            result = clean_json_response(response.text)

            # Defensive post-processing for concept_name and cognitive_level
            if qm_lookup and isinstance(result, dict) and "mistakes" in result:
                for m in result.get("mistakes", []):
                    q_lbl = str(m.get("question_num", "")).strip()
                    if q_lbl in qm_lookup:
                        matched_meta = qm_lookup[q_lbl]
                        if not m.get("concept_name"):
                            m["concept_name"] = matched_meta.get("concept_name") or matched_meta.get("subtopic") or ""
                        if not m.get("cognitive_level"):
                            m["cognitive_level"] = matched_meta.get("cognitive_level") or matched_meta.get("difficulty") or ""

            result = _ensure_question_corrections(
                result=result,
                student_pdf_bytes=student_pdf_bytes,
                marking_key=marking_key,
                total_marks=total_marks,
                api_key=api_key,
                questions_metadata=questions_metadata,
            )
            return result
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Grading failed across models: {last_err}")


def _ensure_question_corrections(
    result: Dict[str, Any],
    student_pdf_bytes: bytes,
    marking_key: Dict[str, Any],
    total_marks: float,
    api_key: Optional[str] = None,
    questions_metadata: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Recover question-level corrections when the first grading response omits them.

    Gemini occasionally returns a reduced score with an empty or incomplete
    ``mistakes`` list. A short audit request makes the correction report useful
    and prevents a score/corrections mismatch.
    """
    if not isinstance(result, dict):
        return result

    # Always fill the official answer from the key when the model omitted it.
    # This guarantees the generated report can print ``Question (correct
    # answer)`` even when Gemini only returned a question label.
    key_lookup = {str(label).strip().lower(): answer for label, answer in marking_key.items()}
    metadata_lookup = {
        str(qm.get("item_label") or qm.get("num") or "").strip(): qm
        for qm in (questions_metadata or [])
        if str(qm.get("item_label") or qm.get("num") or "").strip()
    }
    for mistake in result.get("mistakes", []) if isinstance(result.get("mistakes"), list) else []:
        if not isinstance(mistake, dict):
            continue
        label = str(mistake.get("question_num", "")).strip()
        bare_label = label[3:].strip() if label.lower().startswith("qn ") else label
        if not str(mistake.get("correct_answer", "")).strip():
            answer = key_lookup.get(bare_label.lower())
            if answer is not None:
                mistake["correct_answer"] = str(answer)
        matched_meta = metadata_lookup.get(bare_label) or metadata_lookup.get(label)
        if matched_meta:
            mistake.setdefault("concept_name", matched_meta.get("concept_name") or matched_meta.get("subtopic") or "")
            mistake.setdefault("cognitive_level", matched_meta.get("cognitive_level") or matched_meta.get("difficulty") or "")

    try:
        score = float(result.get("score", total_marks))
        total = float(result.get("total_marks", total_marks) or total_marks)
    except (TypeError, ValueError):
        return result
    existing = result.get("mistakes") if isinstance(result.get("mistakes"), list) else []
    lost = max(0.0, total - score)
    recorded_loss = sum(
        float(m.get("marks_lost", 0) or 0)
        for m in existing
        if isinstance(m, dict)
    )
    if lost <= 0.01 or recorded_loss >= lost - 0.01:
        return result

    key_formatted = json.dumps(marking_key, indent=2)
    audit_prompt = f"""Audit the attached handwritten homework against this official marking key:
{key_formatted}

The marker awarded {score} out of {total} marks, so {lost:g} marks were lost.
Return every question that lost any marks. This is a correction audit, so do
not omit blank answers or questions with partial credit. The correct answer
must be copied exactly from the marking key.

Respond with JSON only:
{{"mistakes": [{{"question_num": "1", "status": "Incorrect", "marks_lost": 1.0,
"student_answer": "", "correct_answer": "...", "error_type": "...",
"details": "..."}}]}}
"""
    try:
        client = get_client(api_key)
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[types.Part.from_bytes(data=student_pdf_bytes, mime_type="application/pdf"), audit_prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
        )
        audit = clean_json_response(response.text)
        recovered = audit.get("mistakes", []) if isinstance(audit, dict) else []
        if isinstance(recovered, list) and recovered:
            merged = {}
            for mistake in existing + recovered:
                if not isinstance(mistake, dict):
                    continue
                label = str(mistake.get("question_num", "")).strip()
                if label:
                    merged[label] = mistake
            result["mistakes"] = list(merged.values())
    except Exception:
        # Keep the original grade if the audit request fails; the caller still
        # receives the score and any corrections returned by the first pass.
        pass
    return result


def grade_combined_student_submissions(
    student_pdf_bytes: bytes,
    marking_key: Dict[str, Any],
    total_marks: float,
    worksheet_title: str = "",
    term: int = 1,
    week: int = 1,
    api_key: Optional[str] = None,
    questions_metadata: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """Grade a PDF containing multiple students' submissions in one pass.

    Gemini identifies each student's page range and returns one normal grading
    record per student. Reports and database submissions are still created
    individually by the calling workflow.
    """
    client = get_client(api_key)
    key_formatted = json.dumps(marking_key, indent=2)
    meta_lines = []
    for qm in questions_metadata or []:
        lbl = str(qm.get("item_label") or qm.get("num") or "").strip()
        c_name = qm.get("concept_name") or qm.get("subtopic") or ""
        c_lvl = qm.get("cognitive_level") or qm.get("difficulty") or ""
        if lbl and (c_name or c_lvl):
            meta_lines.append(f"   - Question {lbl}: Concept = '{c_name}', Cognitive Level = '{c_lvl}'")
    meta_section = "\nQUESTION CONCEPT & COGNITIVE LEVEL MAPPING:\n" + "\n".join(meta_lines) if meta_lines else ""
    prompt = f"""You are a Senior Math Examiner for DA Tuition. The attached PDF contains one or more students' completed homework submissions, usually separated by a name page or a new copy of the worksheet.

Identify every separate student submission and grade each one against this official marking key:
{key_formatted}

TOTAL MARKS PER STUDENT: {total_marks}
HEADER CONTEXT: Term {term} Week {week} Homework ({worksheet_title})
{meta_section}

For each student, identify their name and the page range you graded. Apply the same scoring and diagnostic rules as a single submission: compare every answer, award partial marks where justified, and list every lost mark with question number, status, correct answer, error type, and details. The score and accuracy must agree exactly.
If a student's score is below the total, their `mistakes` list must contain one correction row for every question that lost marks. Never return an empty mistakes list for a student with a non-perfect score.

Respond with valid JSON only in this shape:
{{
  "submissions": [
    {{
      "extracted_name": "Student Name",
      "page_range": "1-4",
      "score": 18.0,
      "total_marks": {total_marks},
      "accuracy_pct": 100.0,
      "mistakes": [],
      "summary_text": "Short tutor summary."
    }}
  ]
}}
"""
    models_to_try = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
    last_err = None
    pdf_part = types.Part.from_bytes(data=student_pdf_bytes, mime_type="application/pdf")
    qm_lookup = {
        str(qm.get("item_label") or qm.get("num") or "").strip(): qm
        for qm in (questions_metadata or [])
        if str(qm.get("item_label") or qm.get("num") or "").strip()
    }
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[pdf_part, prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0)
            )
            raw = clean_json_response(response.text)
            records = raw.get("submissions", []) if isinstance(raw, dict) else raw
            if not isinstance(records, list):
                raise ValueError("Combined marking response did not contain a submissions list")
            for record in records:
                for mistake in record.get("mistakes", []) or []:
                    q_lbl = str(mistake.get("question_num", "")).strip()
                    if q_lbl in qm_lookup:
                        matched = qm_lookup[q_lbl]
                        mistake.setdefault("concept_name", matched.get("concept_name") or matched.get("subtopic") or "")
                        mistake.setdefault("cognitive_level", matched.get("cognitive_level") or matched.get("difficulty") or "")
            return records
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Combined grading failed across models: {last_err}")

# --- 3. TARGETED REMEDIAL & NESA PRACTICE WORKSHEET GENERATOR ---
def generate_remedial_worksheet(
    student_name: str,
    year_level: str,
    weak_topics: List[str],
    num_questions: int = 5,
    worksheet_type: str = "Remedial",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generates a personalized practice worksheet tailored to weak topics.
    Supported worksheet_type values:
    - 'Remedial' -> 'DA Tuition - {student_name} Remedial Practice Worksheet' (Foundational drills & error remediation)
    - 'Targeted NESA' -> 'DA Tuition - {student_name} Targeted NESA Practice Worksheet' (Authentic NSW NESA syllabus exam-style)
    """
    client = get_client(api_key)
    topics_list_str = ", ".join(weak_topics) if weak_topics else "General Revision"

    is_nesa = "nesa" in str(worksheet_type).lower()
    if is_nesa:
        sheet_title = f"DA Tuition - {student_name} Targeted NESA Practice Worksheet"
        role_description = f"You are a Senior NSW Mathematics Curriculum Specialist at DA Tuition creating a 'Targeted NESA Practice Worksheet' for {student_name}."
        focus_instruction = f"Design {num_questions} authentic NSW NESA exam-style questions targeting the student's specific weak topics ({topics_list_str}). Each question should test syllabus mastery and exam application."
    else:
        sheet_title = f"DA Tuition - {student_name} Remedial Practice Worksheet"
        role_description = f"You are a Specialist Math Tutor at DA Tuition creating a 'Remedial Practice Worksheet' for {student_name}."
        focus_instruction = f"Design {num_questions} step-by-step diagnostic remedial drill questions addressing the student's errors in ({topics_list_str}). Each question should unblock misconceptions and reinforce core prerequisite skills."

    prompt = f"""{role_description}

STUDENT: {student_name}
YEAR LEVEL: {year_level}
WEAK TOPICS IDENTIFIED FROM RECENT HOMEWORK:
{topics_list_str}

NUMBER OF QUESTIONS: {num_questions} (Each worth strictly 1 mark)
FOCUS: {focus_instruction}

{get_stage6_syllabus_boundary_prompt(year_level)}

STRICT LATEX RULES:
All math expressions MUST be in LaTeX enclosed in single dollar signs $...$.

OUTPUT FORMAT:
Respond with valid JSON ONLY:
{{
  "title": "{sheet_title}",
  "topic": "Targeted Revision ({topics_list_str})",
  "year_level": "{year_level}",
  "worksheet_type": "{"Targeted NESA" if is_nesa else "Remedial"}",
  "total_marks": {num_questions},
  "questions": [
    {{
      "item_label": "1",
      "text": "...",
      "marks": 1,
      "subtopic": "...",
      "solution_steps": "...",
      "correct_answer": "..."
    }}
  ],
  "marking_key": {{
    "1": "..."
  }}
}}
"""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.3
    )
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=config
    )
    prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
    candidates_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0
    total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) if hasattr(response, 'usage_metadata') else 0
    est_cost = estimate_gemini_cost(prompt_tokens, candidates_tokens, model="gemini-3.8-flash")

    data = clean_json_response(response.text)
    data["meta_tokens"] = total_tokens
    data["meta_cost"] = round(est_cost, 5)
    data["model_used"] = "gemini-3.8-flash"
    if not data.get("title"):
        data["title"] = sheet_title
    data["worksheet_type"] = "Targeted NESA" if is_nesa else "Remedial"
    return audit_and_sanitize_year11_advanced_data(data, year_level, strict=True)

# --- 4. THEORY BOOKLET GENERATOR (TEACHER & STUDENT EDITIONS) ---
def normalize_difficulty(diff: str) -> str:
    """Converts difficulty string into one of the 5 standard pedagogical tiers:
    Section 1 - Commit to Memory, Section 2 - Further Practice, Section 3 - Application, Section 4 - Thinking Creatively, Section 5 - Exam Questions.
    """
    d = str(diff or "").strip()
    d_lower = d.lower()
    if "further" in d_lower or "deeper" in d_lower or "understanding" in d_lower or "medium" in d_lower or "level 2" in d_lower or "section 2" in d_lower:
        return "Section 2 - Further Practice"
    elif "commit" in d_lower or "memory" in d_lower or "drilling" in d_lower or "practice" in d_lower or "easy" in d_lower or "refresher" in d_lower or "level 1" in d_lower or "section 1" in d_lower:
        return "Section 1 - Commit to Memory"
    elif "creative" in d_lower or "thinking" in d_lower or "extremely" in d_lower or "challenging" in d_lower or "distinction" in d_lower or "level 4" in d_lower or "section 4" in d_lower:
        return "Section 4 - Thinking Creatively"
    elif "hard" in d_lower or "application" in d_lower or "level 3" in d_lower or "applying" in d_lower or "section 3" in d_lower:
        return "Section 3 - Application"
    elif "exam" in d_lower or "past" in d_lower or "hsc" in d_lower or "level 5" in d_lower or "section 5" in d_lower:
        return "Section 5 - Exam Questions"
    res = d if d else "Section 1 - Commit to Memory"
    return re.sub(r"\bLevel\b", "Section", res, flags=re.IGNORECASE)

def generate_theory_booklet(
    year_level: str,
    topic: Union[str, List[str]],
    subtopics: Optional[List[str]] = None,
    examples_per_concept: int = 2,
    practice_per_concept: int = 3,
    checking_per_concept: int = 2,
    term: Optional[int] = None,
    week: Optional[int] = None,
    custom_instructions: str = "",
    textbook: str = "CambridgeMATHS NSW",
    api_key: Optional[str] = None,
    question_distribution: Optional[Dict[str, Any]] = None,
    level_distribution: Optional[Dict[str, int]] = None,
    textbook_reference: str = "",
    **kwargs
) -> Dict[str, Any]:
    """
    Generates a comprehensive Theory Booklet for DA Tuition aligned with NSW syllabus textbooks (Cambridge / Maths in Focus).
    Produces rich concept theory, key formula boxes, teacher demonstration examples (with full whiteboard solutions),
    and tiered practice questions (Level 1 - Commit to Memory, Level 2 - Further Practice, Level 3 - Application, Level 4 - Thinking Creatively, Level 5 - Exam Questions).
    """
    client = get_client(api_key)

    if "selected_subtopics" in kwargs and not subtopics:
        subtopics = kwargs["selected_subtopics"]
    if "custom_notes" in kwargs and not custom_instructions:
        custom_instructions = kwargs["custom_notes"]
    if "question_distribution" in kwargs and not question_distribution:
        question_distribution = kwargs["question_distribution"]
    if "level_distribution" in kwargs and not level_distribution:
        level_distribution = kwargs["level_distribution"]

    # Handle single or multi-topic inputs
    if isinstance(topic, list):
        topic_list = [str(t).strip() for t in topic if str(t).strip()]
        topic_str = format_combined_topics(topic_list)
        is_multi_topic = len(topic_list) > 1
    else:
        topic_list = [str(topic).strip()]
        topic_str = clean_topic_title(str(topic))
        is_multi_topic = False

    if not subtopics:
        subtopics = []
        for t in topic_list:
            try:
                subs = get_curriculum_subtopics(year_level, t, textbook=textbook)
                if is_multi_topic:
                    t_clean = clean_topic_title(t)
                    subtopics.extend([f"[{t_clean}] {s}" for s in subs])
                else:
                    subtopics.extend(subs)
            except Exception:
                subtopics.append(t)
        if not subtopics:
            subtopics = [topic_str]

    subtopics_bullet_list = "\n".join([f"- {s}" for s in subtopics])

    teacher_examples_count = max(1, int(examples_per_concept))
    student_practice_count = max(1, int(practice_per_concept))
    checking_questions_count = max(0, int(checking_per_concept))
    total_teacher_examples = teacher_examples_count + 1
    total_practice_questions = student_practice_count + 1

    multi_topic_prompt = ""
    if is_multi_topic:
        multi_topic_prompt = f"- Multi-Topic Booklet Coverage: This booklet covers {len(topic_list)} topics/chapters: {topic_str}. Ensure balanced coverage across all selected subtopics and topics.\n"

    dist_prompt = ""
    if question_distribution:
        dist_lines = []
        for sub, tiers in question_distribution.items():
            tier_strs = [f"{tier}: {cnt} question{'s' if cnt != 1 else ''}" for tier, cnt in tiers.items() if cnt > 0]
            if tier_strs:
                dist_lines.append(f"  * For concept \"{sub}\": {', '.join(tier_strs)}")
        if dist_lines:
            dist_prompt = "- Exact Question Tier Breakdown Per Subtopic (MANDATORY):\n" + "\n".join(dist_lines) + "\n"
    elif level_distribution:
        tier_strs = [f"{tier}: {cnt} question{'s' if cnt != 1 else ''}" for tier, cnt in level_distribution.items() if cnt > 0]
        if tier_strs:
            dist_prompt = f"- Exact Question Tier Breakdown Per Concept (MANDATORY): Each concept must have: {', '.join(tier_strs)}.\n"

    textbook_reference = str(textbook_reference or "").strip() or get_textbook_exercise_reference(textbook, year_level, topic_str)
    reference_prompt = ""
    if textbook_reference:
        reference_prompt = f"""
TEXTBOOK EXERCISE REFERENCE (TEACHER-SUPPLIED LOCAL COPY):
Use this excerpt to align the sequence, notation, and difficulty of the Teacher Demonstration Examples.
For each selected chapter exercise, model the first few exercise questions and explain the same method with fresh numbers and wording. Do not copy the source verbatim and do not reproduce textbook answers.
{textbook_reference}
"""

    yl_lower = str(year_level).lower()
    is_senior_stage6 = any(k in yl_lower for k in ["11", "12", "hsc", "prelim"])
    if is_senior_stage6:
        exam_style_demo_title_example = "Exam Style: NSW HSC / Trial Style Question"
        exam_style_demo_desc = "An authentic exam-style / NSW HSC / Trial question that synthesizes concepts or tests higher-order problem solving under exam conditions."
        exam_style_practice_desc = 'Labeled with difficulty "Level 5 - Exam Questions" (authentic NSW Trial/HSC style challenge, 3-5 marks).'
    else:
        exam_style_demo_title_example = "Exam Style: Authentic Multi-Step Exam Question"
        exam_style_demo_desc = f"An authentic multi-step exam / selective / advanced question suitable for junior students ({year_level}) that synthesizes concepts or tests higher-order problem solving under exam conditions. CRITICAL: NEVER label or reference 'NSW HSC' or 'HSC Trial' for junior years (Years 7-10)."
        exam_style_practice_desc = f'Labeled with difficulty "Level 5 - Exam Questions" (authentic multi-step exam/extension style challenge for {year_level}, 3-5 marks. NEVER reference "NSW HSC" for junior years).'

    prompt = f"""You are a Master Mathematics Educator and Curriculum Director at DA Tuition in Australia, using the {textbook} Stage 4/5/6 NSW syllabus.
Generate a comprehensive, publication-quality THEORY BOOKLET for teaching {year_level}.

BOOKLET SPECIFICATIONS:
- Year Level: {year_level}
- Main Topic / Chapter: {topic_str}
- Textbook Reference: {textbook}
- Term / Week: {f'Term {term}, Week {week}' if (term and week) else 'General Resource / Independent of Term or Week'}
- Concepts / Subtopics to cover in this booklet:
{subtopics_bullet_list}
{multi_topic_prompt}- Teacher Demonstration Examples per concept: {total_teacher_examples} (composed of {teacher_examples_count} progressive foundation-to-application examples + 1 MANDATORY Exam-Style demonstration example)
- Student Practice Questions per concept: {total_practice_questions} (composed of {student_practice_count} progressive practice questions [Level 1, Level 2, ...] + 1 MANDATORY Exam-Style practice question [Exam Style])
- Checking Understanding Questions per concept: {checking_questions_count} (short questions immediately after the demonstrations; students answer these independently in the booklet)
{dist_prompt}{f'- Special Tutor Instructions: {custom_instructions}' if custom_instructions else ''}
{reference_prompt}
- LANGUAGE REQUIREMENT: STRICT AUSTRALIAN ENGLISH SPELLING throughout (e.g. 'factorise', 'rationalise', 'centre', 'metres', 'centimetres', 'labelled', 'modelling', 'colour', 'behaviour', 'minimise', 'maximise', 'summarise'). NEVER use US spellings.

{get_stage6_syllabus_boundary_prompt(year_level, topic_str)}

PEDAGOGICAL APPROACH: IN-CLASS CENTRE TEACHING (CONCISE, DIRECT & TO THE POINT) — MAXIMUM WOW FACTOR:
1. DESIGNED FOR ACTIVE IN-CLASS TEACHING AT DA TUITION: This theory booklet is used during live classroom sessions where students, parents, and teachers expect an elite, high-distinction unfair advantage over standard school teaching. The notes must provide an instant "Aha!" moment and a massive WOW factor every time students read them.
2. CONCISE & TO THE POINT (ZERO FLUFF, NO UNNECESSARY INFO, NO BORING TEXTBOOK PROSE):
   - Do NOT write lengthy paragraphs, conversational analogies (e.g. vending machines), or dry textbook-style backstories.
   - Do NOT repeat the exact same formula 4 times across definition, rules, method, and key formulas.
   - Eliminate all unnecessary filler: every single line must deliver high-yield exam insights, memory hooks, or concrete procedural methods that prove why DA Tuition is the best.
3. THE 3 ELITE DA SIGNATURE PILLARS (MANDATORY IN `theory_content`):
   Structure `theory_content` using ONLY these 3 high-impact, prestigious sections:
   - **The Big Idea (How to Think About It)**: 1 to 2 punchy, memorable sentences explaining the core concept using clear, everyday language that any student instantly visualizes and understands.
     * MANDATORY - EVERYDAY CONVERSATIONAL LANGUAGE (ZERO TECHNICAL JARGON):
       - Explain the concept like a friendly, expert tutor speaking naturally across the desk to a 14-year-old student.
       - STRICTLY AVOID stiff, academic, or overly technical wording. Do NOT write convoluted phrases like "pool their counts together", "identical factors cancel out in pairs", or "algebraic manifestations".
       - Use concrete everyday words and analogies: "copies of a number", "shortcut for", "stacking up", "knocking out", "undoing", "balancing", "growth factor".
       - Example (Index Laws): "An index is just a shortcut counter for how many copies of a number you are multiplying together ($x^3$ just means 3 copies of $x$). Multiplying adds more copies to the stack so you add powers ($x^3 \\times x^2 = x^5$); dividing knocks matching copies off from the top and bottom so you subtract powers ($x^5 \\div x^2 = x^3$)."
       - Example (Compound Interest): "Compound interest is the Snowball Effect: you earn interest on your starting money, and then you earn extra interest on top of the interest you already made."
    - **DA Master Method (The Ninja Recipe)**: Exactly 2 to 3 rapid, actionable steps ([Step 1: Action Tag], [Step 2: Action Tag], [Step 3: Action Tag]) showing the student the exact repeatable routine to solve any question in 30 seconds.
      * STEP FORMAT RULE: Format each step on its own brand-new line starting with a bracketed action tag followed by the instruction, e.g.:
        [Step 1: Big Numbers First] Multiply or divide regular numerical coefficients normally.
        [Step 2: Same Bases Only] Identify matching base pronumerals and add/subtract powers.
        [Step 3: Alphabetical Combine] Write variables in alphabetical order.
        CRITICAL: Each step MUST start on its own new line. NEVER run all steps together in a single continuous paragraph. NEVER write duplicate step numbers like "[Step 1] - [Step 1: ...]".
    - **The Examiner's Trap (Mark Protector)**: The #1 hidden ambush that exam writers use to catch 70% of students in NSW exams, plus the foolproof DA self-check rule to guarantee full marks.
4. MAXIMUM BREVITY & IMPACT: Keep each section concise, sharp, and punchy (approx. 50 to 90 words total) so that the theory box fits cleanly at the top of the concept page alongside formulas and diagrams, leaving maximum room for teacher demonstration examples and student practice on the same page.

REQUIREMENTS FOR EACH CONCEPT:
1. CONCISE IN-CLASS THEORY NOTES (`theory_content`):
   - Provide the 3 signature DA pillars above (**The Big Idea**, **DA Master Method**, **The Examiner's Trap**).
   - Keep it concise, sharp, and to the point—the teacher will provide the verbal elaboration in class.
   - SEPARATE FORMULA RULES ON DISTINCT LINES (`key_formulas`):
     * List all essential formulas in `key_formulas` with clean LaTeX paired with clear, friendly variable definitions in plain English.
     * When covering multiple rules or laws (e.g. First Index Law, Second Index Law, Power of a Power, Coefficients Rule), provide EACH rule as a separate distinct entry in the `key_formulas` list.
     * Geometry & Angle Theorems: When covering angle relationships, provide EACH angle rule as its own separate entry including the rule name, formula, and standard geometric reason in brackets with the parallel lines or shape indicated:
       - "Alternate Angles: $\\angle ABC = \\angle BCD$ (alternate angles, $AB \\parallel CD$, forming a 'Z' shape)"
       - "Corresponding Angles: $\\angle EAB = \\angle ACD$ (corresponding angles, $AB \\parallel CD$, forming an 'F' shape)"
       - "Co-interior Angles: $\\angle BAC + \\angle ACD = 180^\\circ$ (co-interior angles, $AB \\parallel CD$, forming a 'C' shape)"
       - "Angle Sum of a Triangle: $\\angle A + \\angle B + \\angle C = 180^\\circ$ (angle sum of $\\triangle ABC$)"
       - "Exterior Angle of a Triangle: $\\angle ACD = \\angle A + \\angle B$ (exterior angle of $\\triangle ABC$ equals sum of interior opposite angles)"
       - "Vertically Opposite Angles: $\\angle a = \\angle b$ (vertically opposite angles)"
       - "Angles on a Straight Line: $\\angle a + \\angle b = 180^\\circ$ (angles on a straight line are supplementary)"
       - "Angles at a Point: $\\angle a + \\angle b + \\angle c = 360^\\circ$ (angles at a point / revolution)"
     * Example:
       "key_formulas": [
         "First Index Law (Multiplication): $a^m \\times a^n = a^{{m+n}}$ ($a = \\text{{base}}, m, n = \\text{{indices}}$)",
         "Second Index Law (Division): $a^m \\div a^n = \\frac{{a^m}}{{a^n}} = a^{{m-n}}$ ($a \\neq 0$)",
         "Coefficients Rule: $c_1 a^m \\times c_2 a^n = (c_1 \\times c_2) a^{{m+n}}$"
       ]
     * This guarantees every formula law displays cleanly on its own separate line in the booklet.
   - Include a practical 1-sentence exam-room hack or mental shortcut in `tutor_tips`.
   - ILLUSTRATIVE DIAGRAMS INSIDE THEORY/NOTES BOX: For any concept involving visual structures, geometric figures, angles, network concepts (vertices, edges, loops, degrees, trees), coordinate geometry, graphs/curves, trigonometry, vectors, probability trees, or financial timelines, provide a clean, compilable LaTeX TikZ diagram enclosed in \\begin{{center}}\\begin{{tikzpicture}}...\\end{{tikzpicture}}\\end{{center}} in `tikz_diagram`. This diagram is rendered directly INSIDE the Masterclass Theory Box to visually illustrate the concept before the teacher begins the demonstration examples.
   - DIAGRAM & TABLE FORMATTING RULES (CRITICAL):
     * Label clearance: Size boxes to fit their full text, leave visible gaps between neighbouring captions, and keep labels outside the shapes they name. Check the final diagram at booklet scale, not only at its original TikZ size.
     * Combinatorics: For ordered/unordered comparisons and factorial countdowns, keep each label inside its own box and separate captions below boxes. Label factorial expansion arrows "Unroll", never "Peel", and leave enough room above the arrows for those labels. Factorial expressions are numbers, not currency: never show a dollar sign before 5 or another factorial value. Keep text inside factorial boxes transparent without separate white label fills. For circular seating, place chair labels outside the table with transparent backgrounds. For sample-space diagrams, place the sample-space title above the event circle with a clear gap.
     * Cartesian Planes: In TikZ, place quadrant labels as stacked nodes safely away from the axes and coordinate points:
       \\node[align=center, font=\\footnotesize] at (2.2, 2.6) {{\\textbf{{Quadrant 1}}\\\\$(+,+)$}}; for Q1, (-2.2, 2.6) for Q2, (-2.2, -2.6) for Q3, (2.2, -2.6) for Q4.
     * Stem-and-Leaf Plots: If displaying stem-and-leaf plots, format strictly as a centered LaTeX tabular with right-aligned stem, vertical dividing bar, left-aligned leaf column, and Key centered below:
       \\begin{{center}}
       \\begin{{tabular}}{{r|l}}
       \\textbf{{Stem}} & \\textbf{{Leaf}} \\\\
       \\hline
       1 & 2 \\quad 9 \\\\
       2 & 0 \\quad 3 \\quad 5
       \\end{{tabular}}\\\\[0.15cm]
       \\textbf{{Key:}} $3 \\mid 1 = 31$
       \\end{{center}}
     * Frequency Distribution Tables: If displaying frequency tables, format strictly as a centered bordered LaTeX tabular:
       \\begin{{center}}
       \\begin{{tabular}}{{|c|c|}}
       \\hline
       \\textbf{{Score}} & \\textbf{{Frequency}} \\\\
       \\hline
       0 & 5 \\\\
       1 & 12 \\\\
       \\hline
       \\end{{tabular}}
       \\end{{center}}
     * Number & Probability lines: Use a wide horizontal axis (width 10cm to 12cm) and stagger label heights so coordinates and text NEVER collide or overlap.
      * Cartesian Graphs & Coordinate Geometry: In TikZ, all plotted points, labels, and intercepts MUST be mathematically exact. For a line $y = mx + c$, the line must pass directly through $(0, c)$ and (-c/m, 0), and any angle of inclination $\theta$ arc MUST be drawn at the exact x-intercept (-c/m, 0) where the line meets the x-axis.
      * STRICTLY FORBIDDEN (|y|): NEVER include equations, relations, examples, or questions with the absolute value of $y$ (such as $|y| = x$, $|x| + |y| = 4$, or $|y| = f(x)$). In NSW Mathematics Advanced, absolute value is strictly applied to $x$ or $f(x)$ (e.g. $y = |f(x)|$).
       * STRICTLY FORBIDDEN (SET NOTATION): NEVER use university/abstract set theory notation, set builder notation, or abstract set symbols (such as set membership in, not-in, for-all, there-exists, set-builder braces, cardinality bars, subset, union, intersection, or blackboard bold R). High school students at this centre do not understand university set theory. State all definitions, conditions, domain, and range in clear, plain English and standard high school inequalities or intervals (e.g. write 'Each $x$-value has at most one $y$-value', 'For all real $x$', '$x \\ge 0$', 'Domain: all real $x$', 'Vertical Line Test: Any vertical line $x = c$ intersects the graph at most once').
      * STRICTLY FORBIDDEN (SIGMA NOTATION): NEVER use capital sigma summation notation (\\sum, \\Sigma, or ∑). Year 10 NSW students have NOT been taught summation notation! Always write formulas and working in plain English: 'Sum of degrees = 2 × number of edges' or 'Sum of degrees = 2e', 'Sum of scores', etc. Write additions out explicitly (e.g. deg(A) + deg(B) + deg(C) = 2e).
      * JUNIOR & INTERMEDIATE ACCESSIBILITY (YEARS 7-10 / STAGE 5): All explanations, definitions, and formulas must be clear, intuitive, and easy to understand for an average Year 10 NSW student (Stage 5.2/5.3).
        - No University Jargon or Negative Exponents: Write present value as $P = \\frac{{A}}{{(1+r)^n}}$, NEVER with negative indices like $P = A(1+r)^{{-n}}$. Always write total interest as $I = A - P$, NEVER obscure expressions like $I = P[(1+r)^n - 1]$.
        - Financial Mathematics Clarity:
          * Compound Interest: Explain intuitively as the "snowball effect" (interest earned on previously accumulated interest). Clearly define every variable: $A = \\text{{future value (final amount)}}$, $P = \\text{{principal (starting amount)}}$, $r = \\text{{rate per period (as decimal)}}$, $n = \\text{{total number of periods}}$.
          * Fractional Compounding Periods: Emphasize the golden rule: "Divide the annual rate, multiply the number of years" ($r = \\frac{{r_{{\\text{{annual}}}}}}{{k}}$, $n = \\text{{years}} \\times k$).
          * Asset Depreciation: Clearly contrast Straight-Line ($S = V_0 - Dn$, constant dollar reduction each year) with Declining-Balance ($S = V_0(1-r)^n$, constant percentage reduction each year where value drops rapidly at first then flattens).
          * Credit Cards: Clearly explain the billing cycle (30 days) and payment window (25 days, up to 55 days interest-free). State the golden rule: paying the closing balance in FULL by the due date avoids all interest ($0 interest). Paying late or partially triggers interest on the entire original transaction amount from the date of purchase at daily rate $r = \\frac{{r_{{\\text{{annual}}}}}}{{365}}$.
          * Superannuation: Explain super as compulsory employer retirement investments (11.5% super guarantee). Contrast asset risk vs return: Cash (lowest risk, preserves capital) vs Balanced (moderate risk/growth, default fund) vs High Growth (shares/property, highest long-term growth, higher volatility).
        - Timelines & Diagram Spacing: In any TikZ timeline (e.g. credit card cycles, compounding periods), use a wide axis (11cm to 12cm) and stacked, double-tiered brackets (e.g. `raise=4pt` for sub-periods and `raise=24pt` for overall period) so text labels NEVER collide or overlap.
      * All TikZ code must be clean, 100% syntactically valid LaTeX.
      * Descriptive labels on coordinate axes (e.g. 'Single intersection', 'Vertical Line', 'Turning point') must use `above right=3pt` or `above=3pt`, with no fill so the page watermark shows through. Circular seating labels must have no fill and sit outside the table.

2. TEACHER DEMONSTRATION EXAMPLES ({total_teacher_examples} TOTAL PER CONCEPT - MANDATORY):
   For EACH concept, provide exactly {total_teacher_examples} worked demonstration examples:
   - Examples 1 to {teacher_examples_count}: Progressive examples building up from foundational understanding (Applying) to multi-step problem solving (Deeper Understanding, Application).
   - Example {total_teacher_examples} (MANDATORY EXAM-STYLE): {exam_style_demo_desc}
   - MANDATORY GRAPH SKETCHING IN SOLUTIONS: Whenever an example asks to "sketch", "plot", "draw the graph", or "graph" a function, curve, or relation (e.g. $y^2 = 4x$, circles, parabolas, exponentials, or relations tested for functions): `solution_diagram_tikz` is STRICTLY MANDATORY. It must contain the complete TikZ coordinate plane with labelled axes, curve, key points, and vertical line test annotations if testing relations vs functions. NEVER return an empty string for `solution_diagram_tikz` when a question asks to sketch!
   - MANDATORY GIVEN DIAGRAMS FOR STUDENTS (HSC / NSW EXAM STANDARD): Students must always be GIVEN diagrams for problems involving networks, graph theory, shortest paths, minimum spanning trees, geometry, bearings, angles of elevation/depression, or trigonometry, unless the problem explicitly awards marks for constructing/drawing the diagram. NEVER describe network vertices and edge weights or geometric configurations solely in text without providing the compilable LaTeX TikZ diagram in `diagram_tikz`.
   - If the problem involves geometric diagrams, vectors, coordinate graphs, networks, or visual proof steps: provide a compilable TikZ diagram in `diagram_tikz` (for problem) and/or `solution_diagram_tikz` (for solution).
   CRITICAL TITLE FORMATTING RULE:
   - In `title`, write ONLY the descriptive topic/skill name (e.g. "Applying: Direct Formula Substitution", "Deeper Understanding: Two-Step Solving", "Application: Contextual Word Problem", "{exam_style_demo_title_example}").
   - DO NOT prefix `title` with "Example 1:" or "Example 2:" because the system automatically labels the example numbers. Repeating "Example" causes duplicate text (e.g. "Example 1: Example 1: Applying") which is strictly forbidden!
   Each example must include:
   - `example_num`: 1, 2, ..., {total_teacher_examples}
   - `title`: Clean descriptive title WITHOUT the word "Example" or numbers
   - `problem_text`: Complete mathematical problem statement with LaTeX.
     * If a question presents multiple options, investment accounts, schemes, plans, or scenarios (e.g. Account 1 and Account 2, Option A and Option B), each option MUST start on its own bulleted line (e.g. '- Account 1: ...\\n- Account 2: ...'), followed by the concluding question prompt (e.g. 'Calculate the total interest...') on its own separate line.
   - `diagram_tikz`: Compilable TikZ diagram for the problem statement (or empty string)
   - `solution_diagram_tikz`: Compilable TikZ diagram for the solution (or empty string)
   - `worked_solution`: Complete whiteboard step-by-step solution showing every single line of working and the mathematical reasoning behind each step.
     * Output direct, professional mathematical working and explanations ONLY.
     * NEVER include internal conversational chatter, reasoning scratchpads, or self-corrections (e.g. 'Wait, let\'s check', 'Let\'s solve carefully', 'Notice this contains...', 'Wait, if the condition...'). Write step-by-step working directly as a master teacher writes on a whiteboard.
     * When solving multi-part questions, label each subpart clearly with (a), (b), (c) on its own separate line, followed by the working for that subpart.
     * When equations are solved across multiple steps, place each equation step on its own new line.
   - `teaching_notes`: Clear tutor explanation highlighting why this method works, common student misconceptions, and how to secure full marks

3. STUDENT PRACTICE QUESTIONS ({total_practice_questions} TOTAL PER CONCEPT - MANDATORY):
   For EACH concept, provide exactly {total_practice_questions} student practice questions:
   - ACCESSIBILITY & CONFIDENCE-BUILDING PEDAGOGY (CRITICAL):
     * In the Theory Booklet, student practice questions must be approachably scaffolded and designed to build confidence. Students are encountering the concept for the first time in class—do NOT intimidate or overwhelm them with confusing trick phrasing, complex fractions, or tedious arithmetic that makes them give up!
     * Question 1 ("Level 1 - Commit to Memory"): MUST be directly accessible and friendly (1-2 marks). Use clean, friendly whole numbers (e.g. $40^\\circ, 60^\\circ, 75^\\circ, 110^\\circ$, small positive integers). Applying the single rule or formula directly should yield the answer cleanly in 1 or 2 steps. This gives students an immediate confidence boost and momentum!
     * Question 2 ("Level 2 - Further Practice"): Smooth, natural progression reinforcing the concept with standard numbers (2-3 marks).
     * Question 3 ("Level 3 - Application"): A clear, practical application or simple worded problem (2-4 marks).
     * Question 4 ("Level 4 - Thinking Creatively"): Extension synthesis (3-4 marks).
     * Clear & Simple Phrasing: State what is given and what to find in clear, plain English. Avoid stiff, confusing academic wording.
     * Scaffolding: For multi-step questions, scaffold with part (a) and part (b) so the student is guided through the stages rather than hitting a wall.
   - Questions 1 to {student_practice_count}: Tiered practice questions labeled with pedagogical difficulty tiers:
     * "Level 1 - Commit to Memory" (foundational recall, direct substitution, 1-2 marks)
     * "Level 2 - Further Practice" (standard multi-step problem solving, 2-3 marks)
     * "Level 3 - Application" (practical applications, worded problems, 2-4 marks)
     * "Level 4 - Thinking Creatively" (complex multi-stage synthesis, 3-4 marks)
   - Question {total_practice_questions} (MANDATORY EXAM-STYLE): {exam_style_practice_desc}
   - Set the `difficulty` field strictly to one of: "Level 1 - Commit to Memory", "Level 2 - Further Practice", "Level 3 - Application", "Level 4 - Thinking Creatively", or "Level 5 - Exam Questions".
   - In `question`, write the complete mathematical question. If comparing multiple options, accounts, or plans (e.g. Account 1 and Account 2), present each option clearly on its own bulleted line, followed by the concluding question prompt on a separate line.
   - MANDATORY GRAPH SKETCHING IN SOLUTIONS: Whenever a question asks to "sketch", "plot", "draw the graph", or "graph": `solution_diagram_tikz` is STRICTLY MANDATORY. Provide the complete TikZ coordinate plane in `solution_diagram_tikz`.
   - MANDATORY QUESTION VARIETY: BALANCED MIX OF DIAGRAM & NON-DIAGRAM QUESTIONS:
     * To reflect authentic examination variety, student practice sets must feature a healthy, balanced mix of question types:
     * In visual, geometric, network, graph, trigonometry, coordinate geometry, or measurement topics:
       - Approximately 35% to 50% of the practice questions (specifically even-numbered questions like Question 2, Question 4, Question 6) MUST be visual interpretation questions with a complete given TikZ diagram provided in `diagram_tikz` (e.g. "For the network shown below...", "In the right-angled triangle below...", "In the planar graph shown below...").
       - The remaining ~50% to 65% of practice questions (specifically odd-numbered questions like Question 1, Question 3, Question 5) MUST be non-diagram questions (purely algebraic drills, calculation from formula, or worded word problems where no diagram is given and `diagram_tikz` is empty `""`).
     * NEVER return a practice question set where 100% of questions have no diagrams!
     * NEVER return a practice question set where all questions are identical in structure! Provide genuine variety where some questions have diagrams and some do not!
   - MANDATORY GIVEN DIAGRAMS FOR STUDENTS (HSC / NSW EXAM STANDARD): Whenever a question is a visual deduction problem or involves networks, graph theory, shortest paths, planar graphs, minimum spanning trees, geometry, bearings, angles of elevation/depression, or trigonometry, students must always be GIVEN the diagram in `diagram_tikz`. NEVER describe network vertices and edge weights or geometric configurations solely in text without providing the compilable LaTeX TikZ diagram in `diagram_tikz`.
   - If the question involves geometric diagrams, vectors, coordinate graphs, networks, or visual proof steps: provide a compilable TikZ diagram in `diagram_tikz` (for question) and/or `solution_diagram_tikz` (for solution).
   - Include complete worked solutions with mark breakdowns (`[1 mark for ..., 1 mark for ...]`).
    - Include a concise `final_answer` for quick verification.

4. CHECKING UNDERSTANDING QUESTIONS ({checking_questions_count} PER CONCEPT):
   - Place these immediately after the Teacher Demonstration Examples in the booklet.
   - Generate exactly {checking_questions_count} short, focused questions per concept (or an empty list when the count is 0).
   - Each question must directly test the method from the demonstrations, include marks, a complete worked solution for the teacher edition, and a concise final answer.
   - These are independent student attempts: the Student Class and Student Private editions must show the question and an empty working box, with no solution printed beside it.

STRICT LATEX RULES:
Every single variable, expression, equation, fraction, or formula MUST be in valid LaTeX enclosed in single dollar signs $...$ (e.g. '$y = mx + b$', '$\\frac{{a}}{{\\sin A}} = \\frac{{b}}{{\\sin B}}$', '$\\vec{{u}} \\cdot \\vec{{v}} = |\\vec{{u}}||\\vec{{v}}|\\cos\\theta$').

CRITICAL JSON ESCAPING:
Inside JSON string values, escape every LaTeX backslash as double backslash (e.g. write '\\\\frac' instead of '\\frac', '\\\\sqrt' instead of '\\sqrt', and '\\\\mathbf' instead of '\\mathbf'). Return strictly valid JSON.

OUTPUT FORMAT:
Respond with valid JSON ONLY matching this exact structure:
{{
  "title": "{year_level} Mathematics - {topic} Theory & Practice Booklet",
  "year_level": "{year_level}",
  "topic": "{topic}",
  "term": {term if term is not None else "null"},
  "week": {week if week is not None else "null"},
  "concepts": [
    {{
      "concept_name": "Exact Name of Subtopic/Concept",
      "theory_content": "- **The Big Idea**: 1-2 punchy intuitive sentences in everyday conversational language (zero technical jargon)...\\n- **DA Master Method**: [Step 1: Action Tag] First algebraic step. [Step 2: Action Tag] Next step. [Step 3: Action Tag] Final verification.\\n- **The Examiner's Trap**: The #1 student pitfall and how to avoid it.",
      "key_formulas": [
        "First Law: $Formula 1$ ($a = \\text{{variable}}$)",
        "Second Law: $Formula 2$ ($a \\neq 0$)"
      ],
      "tutor_tips": "Concise 1-sentence exam tip or student trap...",
      "tikz_diagram": "\\\\begin{{center}}\\\\begin{{tikzpicture}}...\\\\end{{tikzpicture}}\\\\end{{center}} (illustrative visual model or key concept diagram rendered directly inside the theory box, or empty string)",
      "teacher_examples": [
        {{
          "example_num": 1,
          "title": "Applying: Direct Formula Evaluation",
          "problem_text": "Example problem statement with LaTeX...",
          "diagram_tikz": "",
          "solution_diagram_tikz": "",
          "worked_solution": "Full step-by-step whiteboard solution with LaTeX...",
          "teaching_notes": "Prompt for teacher when explaining on the board..."
        }}
      ],
      "checking_understanding_questions": [
        {{
          "q_num": 1,
          "marks": 1,
          "text": "A short question checking the method just demonstrated.",
          "diagram_tikz": "",
          "worked_solution": "Complete teacher solution.",
          "final_answer": "Concise answer"
        }}
      ],
      "practice_questions": [
        {{
          "q_num": 1,
          "difficulty": "Level 1 - Commit to Memory",
          "marks": 1,
          "text": "Foundational formula/algebraic recall drill (no diagram needed, direct calculation)...",
          "diagram_tikz": "",
          "solution_diagram_tikz": "",
          "worked_solution": "Step-by-step solution with mark criteria...",
          "final_answer": "Concise final answer in LaTeX..."
        }},
        {{
          "q_num": 2,
          "difficulty": "Level 2 - Further Practice",
          "marks": 2,
          "text": "In the diagram shown below, determine the value of ... (visual deduction question with given diagram)",
          "diagram_tikz": "\\\\begin{{center}}\\\\begin{{tikzpicture}}...\\\\end{{tikzpicture}}\\\\end{{center}}",
          "solution_diagram_tikz": "",
          "worked_solution": "Step-by-step solution referencing the diagram...",
          "final_answer": "Concise final answer in LaTeX..."
        }},
        {{
          "q_num": 3,
          "difficulty": "Level 3 - Application",
          "marks": 3,
          "text": "Worded contextual application problem without diagram...",
          "diagram_tikz": "",
          "solution_diagram_tikz": "",
          "worked_solution": "Step-by-step solution with mark criteria...",
          "final_answer": "Concise final answer in LaTeX..."
        }},
        {{
          "q_num": 4,
          "difficulty": "Exam Style",
          "marks": 3,
          "text": "Exam-style challenge question with diagram shown below...",
          "diagram_tikz": "\\\\begin{{center}}\\\\begin{{tikzpicture}}...\\\\end{{tikzpicture}}\\\\end{{center}}",
          "solution_diagram_tikz": "",
          "worked_solution": "Step-by-step solution with mark criteria...",
          "final_answer": "Concise final answer in LaTeX..."
        }}
      ]
    }}
  ]
}}
"""

    models_to_try = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
    last_err = None

    for model_name in models_to_try:
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
                max_output_tokens=65536
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            data = clean_json_response(response.text)
            data["title"] = f"{year_level} Mathematics - {topic_str} Theory & Practice Booklet"
            data["year_level"] = year_level
            data["topic"] = topic_str
            data["term"] = term
            data["week"] = week
            data["textbook"] = textbook
            custom_instructions_val = custom_instructions or kwargs.get("custom_notes", "")
            data["custom_instructions"] = custom_instructions_val or ""
            data["custom_notes"] = custom_instructions_val or ""
            data["extra_instructions"] = custom_instructions_val or ""
            data["textbook_reference_used"] = bool(textbook_reference)

            # Normalize difficulty labels across concepts
            for c in data.get("concepts", []):
                for q in c.get("practice_questions", []) or c.get("review_questions", []):
                    if "difficulty" in q:
                        q["difficulty"] = normalize_difficulty(q["difficulty"])
                pqs = c.get("practice_questions", [])
                checking = c.get("checking_understanding_questions", [])
                if not isinstance(checking, list):
                    checking = []
                c["checking_understanding_questions"] = checking[:checking_questions_count]
                c_name = c.get("concept_name", "")
                if pqs and len(pqs) >= 2:
                    from pdf_generator import ensure_concept_practice_question_variety
                    c["practice_questions"] = ensure_concept_practice_question_variety(pqs, c_name, topic_str)
                if not is_senior_stage6:
                    for ex in c.get("teacher_examples", []):
                        if "title" in ex and ex["title"]:
                            ex_t = str(ex["title"])
                            ex_t = re.sub(r'\b(?:NSW\s+)?HSC\s*/\s*Trial\s*Style\s*Questions?\b', '', ex_t, flags=re.IGNORECASE)
                            ex_t = re.sub(r'\b(?:NSW\s+)?HSC\s*/\s*Trial(?:\s+Questions?)?\b', '', ex_t, flags=re.IGNORECASE)
                            ex_t = re.sub(r'\b(?:NSW\s+)?HSC(?:\s+Style)?(?:\s+Questions?)?\b', '', ex_t, flags=re.IGNORECASE)
                            ex_t = re.sub(r'\bTrial\s*Style\s*Questions?\b', '', ex_t, flags=re.IGNORECASE)
                            ex_t = re.sub(r'^[/:,\-\s()]+|[/:,\-\s()]+$', '', ex_t).strip()
                            if not ex_t or ex_t.lower() in ["exam style", "exam questions"]:
                                ex_t = "Exam Style: Authentic Multi-Step Exam Question"
                            ex["title"] = ex_t

            prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            candidates_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            est_cost = estimate_gemini_cost(prompt_tokens, candidates_tokens, model=model_name)
            data["meta_tokens"] = total_tokens
            data["meta_cost"] = round(est_cost, 5)
            data["model_used"] = model_name
            return audit_and_sanitize_year11_advanced_data(data, year_level, strict=True)
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Theory booklet generation failed across models: {last_err}")


# --- 4B. END-OF-TOPIC MASTERY EXAM GENERATOR (1:1 CONCEPT COVERAGE) ---
def generate_topic_mastery_exam(
    theory_booklet: Dict[str, Any],
    year_level: Optional[str] = None,
    topic: Optional[str] = None,
    textbook: str = "CambridgeMATHS NSW",
    term: Optional[int] = None,
    week: Optional[int] = None,
    custom_instructions: str = "",
    api_key: Optional[str] = None,
    questions_per_concept: int = 3,
    concept_counts: Optional[Dict[str, int]] = None,
    use_search: bool = False
) -> Dict[str, Any]:
    """
    Generates an authentic End-of-Topic Mastery Exam with guaranteed 1:1 concept coverage
    directly mapped to the parent Theory Booklet.
    Each concept in the Theory Booklet is tested across balanced cognitive tiers:
    - Level 1 - Commit to Memory (Foundational drill / definitions, 1 mark)
    - Level 2 - Exam Application (Standard multi-step examination questions, 2-3 marks)
    - Level 3 - Extension / Multi-Step / Examiner Trap (Challenging exam problem, 3-4 marks)
    Every question is tagged with `concept_name`, `concept_id`, and `cognitive_level`.
    Supports any questions_per_concept count (including > 4 questions) or per-concept customization via concept_counts.
    """
    client = get_client(api_key)

    tb_content = theory_booklet.get("content") if isinstance(theory_booklet.get("content"), dict) else theory_booklet
    tb_concepts = tb_content.get("concepts", []) or []
    eff_year = year_level or theory_booklet.get("year_level") or tb_content.get("year_level") or "Year 10"
    eff_topic = topic or theory_booklet.get("topic") or tb_content.get("topic") or "General Mathematics"
    eff_tb = theory_booklet.get("textbook") or tb_content.get("textbook") or textbook
    tb_id = theory_booklet.get("id")

    concept_briefs = []
    total_q_count = 0
    if tb_concepts:
        for idx, c in enumerate(tb_concepts, 1):
            c_name = c.get("concept_name") or c.get("name") or f"Concept {idx}"
            f_list = c.get("key_formulas", [])
            f_str = "; ".join([str(f) for f in f_list]) if f_list else "Standard formulas"
            tips = c.get("tutor_tips", "")
            c_cnt = questions_per_concept
            if concept_counts:
                if c_name in concept_counts:
                    c_cnt = concept_counts[c_name]
                elif str(idx) in concept_counts:
                    c_cnt = concept_counts[str(idx)]
                else:
                    for k, v in concept_counts.items():
                        if k.strip().lower() == c_name.strip().lower() or k.strip().lower() in c_name.strip().lower():
                            c_cnt = v
                            break
            total_q_count += c_cnt
            if concept_counts:
                concept_briefs.append(f"Concept {idx}: {c_name} (Target: {c_cnt} question{'s' if c_cnt != 1 else ''})\n   Key Formulas: {f_str}\n   Tutor Insights / Trap: {tips}")
            else:
                concept_briefs.append(f"Concept {idx}: {c_name}\n   Key Formulas: {f_str}\n   Tutor Insights / Trap: {tips}")
    else:
        # Fallback if raw concepts list is missing: derive standard subtopics
        subtopics = get_curriculum_subtopics(eff_year, eff_topic, textbook=eff_tb)
        for idx, s in enumerate(subtopics[:4], 1):
            c_cnt = questions_per_concept
            if concept_counts and s in concept_counts:
                c_cnt = concept_counts[s]
            total_q_count += c_cnt
            if concept_counts:
                concept_briefs.append(f"Concept {idx}: {s} (Target: {c_cnt} question{'s' if c_cnt != 1 else ''})")
            else:
                concept_briefs.append(f"Concept {idx}: {s}")

    if total_q_count <= 0:
        total_q_count = len(concept_briefs) * questions_per_concept
    if total_q_count <= 0:
        total_q_count = questions_per_concept

    concepts_text = "\n\n".join(concept_briefs)

    if concept_counts:
        arch_instruction = f"For each concept listed above, generate the exact number of target questions specified (total {total_q_count} questions) with balanced cognitive depth progressively distributed across Level 1 (Foundational), Level 2 (Application), and Level 3 (Extension / Trap):"
    else:
        arch_instruction = f"For EVERY concept listed above, generate exactly {questions_per_concept} questions (total {total_q_count} questions) with balanced cognitive depth progressively distributed across Level 1 (Foundational), Level 2 (Application), and Level 3 (Extension / Trap):"

    prompt = f"""You are the Lead Mathematics Examination Director for DA Tuition Australia, using the {eff_tb} Stage 4/5/6 NSW curriculum.
Generate a high-stakes, authentic End-of-Topic Mastery Exam for {eff_year} on the topic: {eff_topic}.

PEDAGOGICAL ALIGNMENT & 100% CONCEPT COVERAGE (CRITICAL REQUIREMENT):
The students have just completed learning this topic using their DA Signature Theory Booklet.
This exam MUST test EVERY SINGLE CONCEPT taught in the Theory Booklet with zero blind spots:

THEORY CONCEPTS TO TEST:
{concepts_text}

EXAM QUESTION ARCHITECTURE:
{arch_instruction}
1. Level 1 - Commit to Memory (1 mark):
   - Direct formula recall, algebraic definition, single-step substitution, or identifying key components.
2. Level 2 - Exam Application (2 to 3 marks):
   - Standard NSW examination question, 2-to-3 step calculation, applying formulas to routine problem contexts.
3. Level 3 - Extension / Examiner Trap (3 to 4 marks):
   - Multi-step non-routine synthesis, working backwards, tricky unit/frequency conversions, or questions incorporating the known examiner traps.

DIFFICULTY LEVEL ATTRIBUTE MAPPING:
- Level 1 questions: "difficulty": "Easy"
- Level 2 questions: "difficulty": "Medium"
- Level 3 questions: "difficulty": "Hard" or "Extremely Hard"

{get_stage6_syllabus_boundary_prompt(eff_year, eff_topic)}

DIAGRAMS & TIKZ (MANDATORY WHERE APPROPRIATE):
For geometric questions, coordinate geometry, probability trees, or vector problems, provide clean, 100% compilable TikZ code in "diagram_tikz".

LATEX MATHEMATICAL FORMATTING:
Enclose every equation, variable, number with units, or fraction in single dollar signs $...$ (e.g. '$A = P(1+r)^n$', '$x = 4$').

MULTI-PART QUESTION ARCHITECTURE & SUBPARTS:
When generating multi-step questions (e.g. Level 2 and Level 3):
- State any background stem or problem premise first (e.g. 'A relation is defined by the equation $(x-3)^2 + y^2 = 16$.').
- Clearly delineate subparts with '(a)', '(b)', '(c)' tags (e.g. '(a) By testing $x = 3$, demonstrate why this fails the vertical line test. (b) Split the relation into two separate functions and state the domain of each.').
- In "solution_steps", provide complete line-by-line working with '(a)' and '(b)' clearly separated.
- In "correct_answer", provide concise final answers for all subparts labeled with '(a)' and '(b)'.

OUTPUT FORMAT:
Respond with valid JSON ONLY:
{{
  "title": "{eff_year} Mathematics - {eff_topic} (End-of-Topic Mastery Exam)",
  "topic": "{eff_topic}",
  "year_level": "{eff_year}",
  "term": {term if term is not None else "null"},
  "week": {week if week is not None else "null"},
  "sheet_type": "Topic Mastery Exam",
  "source_theory_id": {tb_id if tb_id is not None else "null"},
  "total_items": {total_q_count},
  "questions": [
    {{
      "item_label": "1",
      "text": "Question text with LaTeX math...",
      "diagram_tikz": "",
      "marks": 1,
      "difficulty": "Easy",
      "concept_name": "Exact Name of Concept Tested",
      "cognitive_level": "Level 1 - Commit to Memory",
      "subtopic": "Subtopic Name",
      "solution_steps": "Complete line-by-line worked solution with LaTeX math...",
      "correct_answer": "Final concise answer"
    }}
  ],
  "marking_key": {{
    "1": "Final Answer 1",
    "2": "Final Answer 2"
  }}
}}
"""

    models_to_try = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
    last_err = None

    for model_name in models_to_try:
        try:
            tools = [types.Tool(google_search=types.GoogleSearch())] if use_search else None
            config = types.GenerateContentConfig(
                response_mime_type="application/json" if not use_search else None,
                temperature=0.2,
                max_output_tokens=65536,
                tools=tools
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            data = clean_json_response(response.text)

            prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            candidates_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            est_cost = estimate_gemini_cost(prompt_tokens, candidates_tokens, model=model_name)
            data["meta_tokens"] = total_tokens
            data["meta_cost"] = round(est_cost, 5)
            data["model_used"] = model_name
            data["source_theory_id"] = tb_id
            data["assessment_type"] = "topic_exam"

            # Ensure marking key is clean
            if "marking_key" not in data or not data["marking_key"]:
                m_key = {}
                for q in data.get("questions", []):
                    lbl = str(q.get("item_label") or q.get("num") or "").strip()
                    if lbl:
                        m_key[lbl] = str(q.get("correct_answer") or q.get("final_answer") or "").strip()
                data["marking_key"] = m_key

            return data
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"End-of-Topic exam generation failed across models: {last_err}")


# --- 4C. ALIGNED COMPANION WORKSHEET GENERATOR (IN-CLASS & HOMEWORK) ---
def generate_aligned_companion_worksheet(
    theory_booklet: Dict[str, Any],
    sheet_type: str = "In-Class",
    concept_counts: Optional[Dict[str, int]] = None,
    difficulty_counts: Optional[Dict[str, Dict[str, int]]] = None,
    set_number: int = 1,
    year_level: Optional[str] = None,
    topic: Optional[str] = None,
    textbook: str = "CambridgeMATHS NSW",
    term: Optional[int] = None,
    week: Optional[int] = None,
    custom_instructions: str = "",
    api_key: Optional[str] = None,
    use_search: bool = False
) -> Dict[str, Any]:
    """
    Generates a 100% pedagogical companion worksheet (In-Class Practice or Homework)
    directly aligned with a parent Theory Booklet.
    Allows specifying exact question counts per concept, and per difficulty for homework.

    Pedagogical Modes:
    - In-Class Practice: Stepped, scaffolded whiteboard practice directly mirroring the teacher examples.
      Question 1 provides guided parallel scaffolding; subsequent questions provide gradual release of responsibility.
    - Homework (Set 1 / Set 2): Numerical twin isomorphic variations with fresh coefficients and constants,
      preserving the algebraic structure so students can reference their Theory Booklet notes at home.
    """
    client = get_client(api_key)

    tb_content = theory_booklet.get("content") if isinstance(theory_booklet.get("content"), dict) else theory_booklet
    tb_concepts = tb_content.get("concepts", []) or []
    eff_year = year_level or theory_booklet.get("year_level") or tb_content.get("year_level") or "Year 10"
    eff_topic = topic or theory_booklet.get("topic") or tb_content.get("topic") or "General Mathematics"
    eff_tb = theory_booklet.get("textbook") or tb_content.get("textbook") or textbook
    tb_id = theory_booklet.get("id")

    normalized_sheet_type = "In-Class" if "in" in str(sheet_type).lower() and "class" in str(sheet_type).lower() else "Homework"
    assessment_type = "in_class" if normalized_sheet_type == "In-Class" else "homework"
    default_q_count = 2 if normalized_sheet_type == "In-Class" else 3
    difficulty_levels = ("Easy", "Medium", "Hard", "Extremely Hard")
    if difficulty_counts is not None and normalized_sheet_type != "Homework":
        raise ValueError("Per-difficulty question counts are available for homework booklets only.")

    def requested_difficulties(name: str, index: int) -> Optional[Dict[str, int]]:
        if difficulty_counts is None:
            return None
        raw = difficulty_counts.get(name, difficulty_counts.get(str(index), {}))
        if not isinstance(raw, dict) or set(raw) - set(difficulty_levels):
            raise ValueError(f"Invalid difficulty allocation for {name}.")
        tiers = {}
        for level in difficulty_levels:
            value = raw.get(level, 0)
            if isinstance(value, bool):
                raise ValueError(f"Invalid {level} question count for {name}.")
            try:
                count = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid {level} question count for {name}.")
            if count < 0 or str(value).strip() != str(count):
                raise ValueError(f"Invalid {level} question count for {name}.")
            tiers[level] = count
        return tiers

    concept_briefs = []
    total_requested = 0
    expected_difficulties: Dict[str, Dict[str, int]] = {}

    if tb_concepts:
        for idx, c in enumerate(tb_concepts, 1):
            c_name = c.get("concept_name") or c.get("name") or f"Concept {idx}"
            tiers = requested_difficulties(c_name, idx)
            
            # Determine question count for this concept
            count = None
            if concept_counts:
                if c_name in concept_counts:
                    count = concept_counts[c_name]
                elif str(idx) in concept_counts:
                    count = concept_counts[str(idx)]
                else:
                    for k, v in concept_counts.items():
                        if k.strip().lower() == c_name.strip().lower() or k.strip().lower() in c_name.strip().lower():
                            count = v
                            break
            if tiers is not None:
                count = sum(tiers.values())
            if count is None:
                count = default_q_count
            
            try:
                count = int(count)
            except (ValueError, TypeError):
                count = default_q_count

            if count <= 0:
                continue

            total_requested += count
            if tiers is not None:
                expected_difficulties[c_name] = tiers
            f_list = c.get("key_formulas", [])
            f_str = "; ".join([str(f) for f in f_list]) if f_list else "Standard formulas"
            tips = c.get("tutor_tips", "")
            
            # Extract prototype examples
            ex_lines = []
            for e_idx, ex in enumerate(c.get("teacher_examples", [])[:2], 1):
                p_text = ex.get("problem_text", "")
                if p_text:
                    ex_lines.append(f"      Prototype Example {e_idx}: {p_text}")
            ex_str = ("\n" + "\n".join(ex_lines)) if ex_lines else ""

            tier_note = ("\n   Exact Difficulty Counts: " + ", ".join(
                f"{level}: {tiers[level]}" for level in difficulty_levels
            )) if tiers is not None else ""
            concept_briefs.append(
                f"Concept {idx}: {c_name} (Requested Questions: {count})\n"
                f"   Key Formulas: {f_str}\n"
                f"   Tutor Insights / Trap to Avoid: {tips}{tier_note}{ex_str}"
            )
    else:
        subtopics = get_curriculum_subtopics(eff_year, eff_topic, textbook=eff_tb)
        for idx, s in enumerate(subtopics[:4], 1):
            tiers = requested_difficulties(s, idx)
            count = sum(tiers.values()) if tiers is not None else default_q_count
            if tiers is None and concept_counts and (s in concept_counts or str(idx) in concept_counts):
                count = concept_counts.get(s, concept_counts.get(str(idx), default_q_count))
            if count > 0:
                total_requested += count
                if tiers is not None:
                    expected_difficulties[s] = tiers
                tier_note = ("; Exact Difficulty Counts: " + ", ".join(
                    f"{level}: {tiers[level]}" for level in difficulty_levels
                )) if tiers is not None else ""
                concept_briefs.append(f"Concept {idx}: {s} (Requested Questions: {count}{tier_note})")

    if total_requested <= 0 or not concept_briefs:
        if difficulty_counts is not None or concept_counts is not None:
            raise ValueError("Select at least one homework question before generating.")
        # Fallback: ensure at least default items
        concept_briefs = [f"Concept 1: {eff_topic} Foundations (Requested Questions: {default_q_count})"]
        total_requested = default_q_count

    concepts_text = "\n\n".join(concept_briefs)
    difficulty_instruction = (
        "- For EACH concept, generate exactly its Easy, Medium, Hard, and Extremely Hard counts listed above. "
        "A zero count means no questions at that difficulty. These counts are mandatory, not suggestions.\n"
        "- Set each question's difficulty field to exactly one of: Easy, Medium, Hard, Extremely Hard.\n"
        if difficulty_counts is not None else
        '- Assign a realistic difficulty level to each question: "Easy", "Medium", "Hard", or "Extremely Hard".\n'
        '- Early questions for each concept should be "Easy" or "Medium"; later questions can be "Hard".\n'
    )

    if normalized_sheet_type == "In-Class":
        sheet_title = f"{eff_year} Mathematics - {eff_topic} (In-Class Practice)"
        pedagogical_instructions = f"""PEDAGOGICAL PURPOSE: IN-CLASS GUIDED WHITEBOARD PRACTICE
The students are currently in class with the teacher.
They have just reviewed the theory notes and worked examples in their Theory Booklet.
YOUR MISSION:
1. For each concept, generate EXACTLY the requested number of questions.
2. Question 1 for each concept MUST be a stepped, scaffolded practice problem directly reinforcing the prototype teacher example from the Theory Booklet.
3. Subsequent questions for that concept should gradually release responsibility, giving students confidence to solve on the whiteboard or independently.
4. Keep numerical values clean and accessible for live classroom working."""
    else:
        sheet_title = f"{eff_year} Mathematics - {eff_topic} (Homework - Set {set_number})"
        pedagogical_instructions = f"""PEDAGOGICAL PURPOSE: HOMEWORK NUMERICAL TWINS & MASTERY REINFORCEMENT (SET {set_number})
The students are completing this booklet independently at home.
They have their Theory Booklet with them as a reference.
YOUR MISSION:
1. For each concept, generate EXACTLY the requested number of questions.
2. EVERY SINGLE QUESTION must be a NUMERICAL TWIN / ISOMORPHIC VARIATION of the theory concepts and teacher examples.
3. Maintain the exact algebraic framework, question phrasing, and trap-avoidance structures, but change the numerical constants, coordinates, and coefficients.
4. Students MUST be able to open their Theory Booklet, find the matching worked example, and self-guide through the problem without confusion or frustration."""

    prompt = f"""You are the Master Curriculum Director for DA Tuition Australia, developing companion practice materials using the {eff_tb} Stage 4/5/6 NSW curriculum.
Generate a high-quality, authentic {normalized_sheet_type} booklet for {eff_year} on the topic: {eff_topic}.

{pedagogical_instructions}

{get_stage6_syllabus_boundary_prompt(eff_year, eff_topic)}

CONCEPTS AND EXACT QUESTION ALLOCATION:
{concepts_text}

TOTAL QUESTIONS TO GENERATE: EXACTLY {total_requested}

DIFFICULTY LEVEL DISTRIBUTION:
{difficulty_instruction}

PROOF AND REASONING ANSWERS:
- If a question asks students to prove, show, explain, or justify a result, provide the actual line-by-line argument in "solution_steps".
- Never use "Proof as shown", "See solution", or another placeholder as the correct answer or marking key. State the proof or its essential reasoning explicitly.

LATEX MATHEMATICAL FORMATTING:
Enclose all mathematical expressions, equations, coordinates, fractions, and variables in single dollar signs $...$ (e.g. '$y = 2x - 5$', '$\\sqrt{{x+1}}$', '$(3, -4)$').

MULTI-PART QUESTIONS:
Where a question has multiple steps, provide clear subparts '(a)', '(b)' in the text, and complete line-by-line solutions in "solution_steps".

OUTPUT FORMAT:
Respond with valid JSON ONLY:
{{
  "title": "{sheet_title}",
  "topic": "{eff_topic}",
  "year_level": "{eff_year}",
  "term": {term if term is not None else "null"},
  "week": {week if week is not None else "null"},
  "sheet_type": "{normalized_sheet_type}",
  "set_number": {set_number},
  "source_theory_id": {tb_id if tb_id is not None else "null"},
  "assessment_type": "{assessment_type}",
  "total_items": {total_requested},
  "questions": [
    {{
      "item_label": "1",
      "text": "Question text with LaTeX math...",
      "diagram_tikz": "",
      "marks": 2,
      "difficulty": "Medium",
      "concept_name": "Exact Name of Concept Tested",
      "cognitive_level": "Level 2 - Exam Application",
      "subtopic": "Subtopic Name",
      "solution_steps": "Complete step-by-step worked solution...",
      "correct_answer": "Final concise answer"
    }}
  ],
  "marking_key": {{
    "1": "Final Answer 1"
  }}
}}
"""

    models_to_try = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
    last_err = None

    for model_name in models_to_try:
        try:
            tools = [types.Tool(google_search=types.GoogleSearch())] if use_search else None
            config = types.GenerateContentConfig(
                response_mime_type="application/json" if not use_search else None,
                temperature=0.2,
                max_output_tokens=65536,
                tools=tools
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            data = clean_json_response(response.text)

            prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            candidates_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            est_cost = estimate_gemini_cost(prompt_tokens, candidates_tokens, model=model_name)
            data["meta_tokens"] = total_tokens
            data["meta_cost"] = round(est_cost, 5)
            data["model_used"] = model_name
            data["source_theory_id"] = tb_id
            data["assessment_type"] = assessment_type
            data["sheet_type"] = normalized_sheet_type
            data["set_number"] = set_number

            if expected_difficulties:
                questions = data.get("questions")
                if not isinstance(questions, list) or len(questions) != total_requested:
                    raise ValueError(f"Generated {len(questions) if isinstance(questions, list) else 0} questions; requested {total_requested}.")
                def normalized_concept_name(name: str) -> str:
                    name = re.sub(r"^concept\s+\d+\s*[:.\-]\s*", "", str(name).strip(), flags=re.IGNORECASE)
                    return re.sub(r"\s+", " ", name).strip().casefold()

                name_lookup = {normalized_concept_name(name): name for name in expected_difficulties}
                actual = {name: {level: 0 for level in difficulty_levels} for name in expected_difficulties}
                for question in questions:
                    if not isinstance(question, dict):
                        raise ValueError("Generated homework contains an invalid question.")
                    raw_name = normalized_concept_name(question.get("concept_name") or "")
                    concept_name = name_lookup.get(raw_name)
                    if concept_name is None:
                        raise ValueError(f"Generated question has an unknown concept: {question.get('concept_name')!r}.")
                    raw_level = str(question.get("difficulty") or "").strip().casefold()
                    level = next((item for item in difficulty_levels if item.casefold() == raw_level), None)
                    if level is None:
                        raise ValueError(f"Generated question has an invalid difficulty: {question.get('difficulty')!r}.")
                    question["concept_name"] = concept_name
                    question["difficulty"] = level
                    actual[concept_name][level] += 1
                if actual != expected_difficulties:
                    raise ValueError(f"Generated difficulty counts {actual} do not match requested counts {expected_difficulties}.")
                data["total_items"] = total_requested

            for question in data.get("questions", []):
                answer = str(question.get("correct_answer") or question.get("final_answer") or "")
                if re.search(r"\b(?:proof as shown|see (?:the )?(?:proof|solution)|proof omitted)\b", answer, re.IGNORECASE):
                    worked = str(question.get("solution_steps") or question.get("worked_solution") or "").strip()
                    if len(worked) < 20:
                        raise ValueError("A proof question was generated without a usable model proof.")
                    label = str(question.get("item_label") or question.get("num") or "").strip()
                    if label:
                        data.setdefault("marking_key", {})[label] = worked

            # Ensure marking key is clean
            if "marking_key" not in data or not data["marking_key"]:
                m_key = {}
                for q in data.get("questions", []):
                    lbl = str(q.get("item_label") or q.get("num") or "").strip()
                    if lbl:
                        m_key[lbl] = str(q.get("correct_answer") or q.get("final_answer") or "").strip()
                data["marking_key"] = m_key

            return data
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Aligned companion worksheet generation failed across models: {last_err}")


# --- 5. REVIEW & REVISION BOOKLET GENERATOR (EXAM PREP & MASTERY) ---
def generate_review_booklet(
    year_level: str,
    topic: Union[str, List[str]],
    subtopics: Optional[List[str]] = None,
    examples_per_concept: int = 1,
    practice_per_concept: int = 3,
    term: Optional[int] = None,
    week: Optional[int] = None,
    custom_instructions: str = "",
    textbook: str = "CambridgeMATHS NSW",
    api_key: Optional[str] = None,
    question_distribution: Optional[Dict[str, Any]] = None,
    level_distribution: Optional[Dict[str, int]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Generates a dedicated Review & Exam Revision Booklet for DA Tuition students returning to a topic
    for exam prep, yearly exam revision, or mastery consolidation.
    Produces high-yield revision summaries, critical formula reference boxes, tips & tricks / common pitfalls,
    curated mastery exam demonstration examples, and tiered revision questions.
    """
    client = get_client(api_key)

    if "selected_subtopics" in kwargs and not subtopics:
        subtopics = kwargs["selected_subtopics"]
    if "questions_per_concept" in kwargs and practice_per_concept == 3:
        practice_per_concept = kwargs["questions_per_concept"]
    if "custom_notes" in kwargs and not custom_instructions:
        custom_instructions = kwargs["custom_notes"]
    if "question_distribution" in kwargs and not question_distribution:
        question_distribution = kwargs["question_distribution"]
    if "level_distribution" in kwargs and not level_distribution:
        level_distribution = kwargs["level_distribution"]

    # Handle single or multi-topic inputs
    if isinstance(topic, list):
        topic_list = [str(t).strip() for t in topic if str(t).strip()]
        topic_str = format_combined_topics(topic_list)
        is_multi_topic = len(topic_list) > 1
    else:
        topic_list = [str(topic).strip()]
        topic_str = clean_topic_title(str(topic))
        is_multi_topic = False

    if not subtopics:
        subtopics = []
        for t in topic_list:
            try:
                subs = get_curriculum_subtopics(year_level, t, textbook=textbook)
                if is_multi_topic:
                    t_clean = clean_topic_title(t)
                    subtopics.extend([f"[{t_clean}] {s}" for s in subs])
                else:
                    subtopics.extend(subs)
            except Exception:
                subtopics.append(t)
        if not subtopics:
            subtopics = [f"{topic_str} Core Principles", f"{topic_str} Exam Techniques"]

    subtopics_bullet_list = "\n".join([f"- {s}" for s in subtopics])

    multi_topic_prompt = ""
    if is_multi_topic:
        multi_topic_prompt = f"- Multi-Topic Booklet Coverage: This review booklet consolidates {len(topic_list)} topics/chapters: {topic_str}. Organize revision summaries and mastery examples logically across each topic.\n"

    dist_prompt = ""
    if question_distribution:
        dist_lines = []
        for sub, tiers in question_distribution.items():
            tier_strs = [f"{tier}: {cnt} question{'s' if cnt != 1 else ''}" for tier, cnt in tiers.items() if cnt > 0]
            if tier_strs:
                dist_lines.append(f"  * For concept \"{sub}\": {', '.join(tier_strs)}")
        if dist_lines:
            dist_prompt = "- Exact Question Tier Breakdown Per Subtopic (MANDATORY):\n" + "\n".join(dist_lines) + "\n"
    elif level_distribution:
        tier_strs = [f"{tier}: {cnt} question{'s' if cnt != 1 else ''}" for tier, cnt in level_distribution.items() if cnt > 0]
        if tier_strs:
            dist_prompt = f"- Exact Question Tier Breakdown Per Concept (MANDATORY): Each concept must have: {', '.join(tier_strs)}.\n"

    prompt = f"""You are a Master Mathematics Educator and Senior Curriculum Director at DA Tuition in Australia, preparing a publication-quality TOPIC REVIEW & EXAM REVISION BOOKLET for {year_level}.
This booklet is designed for students who covered this topic earlier and are returning to it for exam revision, yearly exam preparation, or mastery consolidation.

BOOKLET SPECIFICATIONS:
- Year Level: {year_level}
- Main Topic / Chapter: {topic_str}
- Textbook Reference: {textbook}
- Term / Week: {f'Term {term}, Week {week}' if (term and week) else 'General Revision / Independent of Term or Week'}
- Concepts / Subtopics to cover in this review booklet:
{subtopics_bullet_list}
{multi_topic_prompt}- Mastery Model Demonstration Examples per concept: {examples_per_concept}
- Tiered Revision Questions per concept: {practice_per_concept} (tiered from Refresher, to Standard Exam, to Distinction Challenge)
{dist_prompt}{f'- Special Tutor Instructions: {custom_instructions}' if custom_instructions else ''}

{get_stage6_syllabus_boundary_prompt(year_level, topic_str)}

PEDAGOGICAL REQUIREMENTS: THOROUGH & ACCESSIBLE SELF-LEARNING REVISION NOTES (SIMPLE, DETAILED, ANTI-TEXTBOOK):
1. COMPREHENSIVE SELF-LEARNING REVISION SUMMARY (`revision_summary`):
   - DESIGNED FOR SELF-LEARNING: The student can read these notes independently and understand the entire concept even without a teacher present.
   - SIMPLE, EASY-TO-UNDERSTAND LANGUAGE: Use simple words, intuitive explanations, and zero dense academic jargon. If introducing any mathematical terms, explain them in plain English.
   - DETAILED & THOROUGH: Provide 4 to 6 detailed, informative bullet points in `revision_summary` that explain the concept thoroughly from scratch.
   - Use bold micro-headers:
     * - **What It Is (From Scratch)**: Clear, simple explanation of the concept from first principles in plain English.
     * - **Rule**: Exact mathematical law or relation in simple English and LaTeX (use '**Rule:**', NEVER 'The High-Yield Rule').
     * - **Visual Intuition**: How to picture this on a graph or sketch.
     * - **Step-by-Step Method**: Numbered action recipe for solving problems.
     * - **Exam Action Trigger**: What keyword or visual clue tells you to apply this method.
     * - **Common Trap & Self-Check**: What mistake loses marks and how to verify your answer.
   - List critical formulas in `key_formulas` in clean LaTeX math with clear explanations of every variable.

2. TIPS, TRICKS & COMMON PITFALLS (`tips_and_tricks` and `common_pitfalls`):
   - `tips_and_tricks`: 1-2 sentence high-leverage examination shortcut, algebraic trick, calculator technique, or tutor secret that saves time and eliminates errors.
   - `common_pitfalls`: A list of 2-3 specific traps where students lose marks in exams (e.g. sign errors, domain restrictions, degree vs radian trap, algebraic cancellation errors).

3. MASTERY MODEL DEMONSTRATION EXAMPLES (`mastery_examples`):
   - Provide {examples_per_concept} typical exam-standard model examples per concept (up to 5).
   - Provide full step-by-step whiteboard solution explaining the mathematical strategy.
   - MANDATORY GIVEN DIAGRAMS FOR STUDENTS (HSC / NSW EXAM STANDARD): Students must always be GIVEN diagrams for examples involving networks, graph theory, shortest paths, minimum spanning trees, geometry, bearings, angles of elevation/depression, or trigonometry, unless the question explicitly awards marks for constructing/drawing the diagram. NEVER describe network vertices and edge weights or geometric configurations solely in text without providing the compilable LaTeX TikZ diagram in `diagram_tikz`.
   - If the example involves geometric figures, curves, vectors, or coordinate graphs: provide a compilable TikZ diagram in `diagram_tikz` (for problem) and/or `solution_diagram_tikz` (for solution).
   - Include `exam_commentary`: Clear insight on why this is tested in exams and key advice on where marks are typically awarded or lost.
   - CRITICAL TITLE FORMATTING RULE: In `title`, write ONLY the concise descriptive topic/skill name (e.g. "Direct Application: Coordinate Distance", "Standard Exam: Circle Geometry Angle Deduction"). DO NOT prepend "Example 1:" or "Mastery Example 1:".

4. REVISION PRACTICE QUESTIONS (`review_questions`):
   - Provide exactly {practice_per_concept} tiered revision questions per concept (up to 50 questions).
    - Order questions progressively across 5 standard pedagogical tiers:
      * Level 1 - Commit to Memory: Direct recall of formulas, basic definitions, and foundational 1-step calculations (1-2 marks each)
      * Level 2 - Further Practice: Standard multi-step calculation and conceptual problem solving (2-3 marks each)
      * Level 3 - Application: Practical applications, worded problems, and geometric deductions (2-4 marks each)
      * Level 4 - Thinking Creatively: Complex multi-stage synthesis and distinction challenge (3-4 marks each)
      * Level 5 - Exam Questions: Authentic NSW exam/trial questions, multi-part synthesis, or proof (3-5 marks each)
    - When large question sets (e.g. 10 to 50 questions) are requested, distribute across tiers proportionally unless an exact breakdown is specified above. Ensure each question provides distinct mathematical variety (different coefficients, contexts, or geometric orientations).
    - Set the `difficulty` field strictly to one of: "Level 1 - Commit to Memory", "Level 2 - Further Practice", "Level 3 - Application", "Level 4 - Thinking Creatively", or "Level 5 - Exam Questions".
   - MANDATORY GRAPH SKETCHING IN SOLUTIONS: Whenever an example or question asks to "sketch", "plot", "draw the graph", or "graph": `solution_diagram_tikz` is STRICTLY MANDATORY. Provide the complete TikZ coordinate plane in `solution_diagram_tikz`.
   - MANDATORY QUESTION VARIETY: BALANCED MIX OF DIAGRAM & NON-DIAGRAM QUESTIONS:
     * To reflect authentic examination variety, review practice sets must feature a healthy, balanced mix of question types:
     * In visual, geometric, network, graph, trigonometry, coordinate geometry, or measurement topics:
       - Approximately 40% to 60% of review questions MUST be visual interpretation questions with a complete given TikZ diagram provided in `diagram_tikz`.
       - The remaining ~40% to 60% of review questions MUST be non-diagram questions (purely algebraic drills, calculation from formula, or worded problems where `diagram_tikz` is empty `""`).
     * NEVER return a review question set where 100% of questions have no diagrams!
     * NEVER return a review question set where all questions are identical in structure! Ensure authentic variety!
   - MANDATORY GIVEN DIAGRAMS FOR STUDENTS (HSC / NSW EXAM STANDARD): Students must always be GIVEN diagrams for questions involving networks, graph theory, shortest paths, planar graphs, minimum spanning trees, geometry, bearings, angles of elevation/depression, or trigonometry, unless the question explicitly awards marks for constructing/drawing the diagram. NEVER describe network vertices and edge weights or geometric configurations solely in text without providing the compilable LaTeX TikZ diagram in `diagram_tikz`.
   - If the question involves geometric figures, curves, vectors, or coordinate graphs: provide a compilable TikZ diagram in `diagram_tikz` (for question) and/or `solution_diagram_tikz` (for solution).
   - LANGUAGE REQUIREMENT: STRICT AUSTRALIAN ENGLISH SPELLING throughout (e.g. 'factorise', 'rationalise', 'centre', 'metres', 'labelled', 'modelling', 'colour', 'behaviour', 'minimise', 'maximise', 'summarise'). NEVER use US spellings.
   - Include complete worked solutions with mark breakdowns (`[1 mark for ..., 1 mark for ...]`).
   - Include concise `final_answer` in LaTeX for quick verification.

5. DIAGRAMS & TABLES (CRITICAL):
   - If relevant (geometry, trigonometry, curves, calculus, probability, statistics), provide clean compilable TikZ or LaTeX tabular specifications in `tikz_diagram` for the concept summary box, or in examples/questions.
   - CARTESIAN PLANES: In TikZ, place quadrant labels as stacked nodes safely away from the axes and coordinate points:
     \\node[align=center, font=\\footnotesize] at (2.2, 2.6) {{\\textbf{{Quadrant 1}}\\\\$(+,+)$}}; for Q1, (-2.2, 2.6) for Q2, (-2.2, -2.6) for Q3, (2.2, -2.6) for Q4.
   - STEM-AND-LEAF PLOTS: If displaying a stem-and-leaf plot, format strictly as a centered LaTeX tabular with right-aligned stem, vertical dividing bar, left-aligned leaf column, and Key centered below:
     \\begin{{center}}
     \\begin{{tabular}}{{r|l}}
     \\textbf{{Stem}} & \\textbf{{Leaf}} \\\\
     \\hline
     1 & 2 \\quad 9 \\\\
     2 & 0 \\quad 3 \\quad 5
     \\end{{tabular}}\\\\[0.15cm]
     \\textbf{{Key:}} $3 \\mid 1 = 31$
     \\end{{center}}
   - FREQUENCY DISTRIBUTION TABLES: If displaying a frequency table, format strictly as a centered bordered LaTeX tabular:
     \\begin{{center}}
     \\begin{{tabular}}{{|c|c|}}
     \\hline
     \\textbf{{Score}} & \\textbf{{Frequency}} \\\\
     \\hline
     0 & 5 \\\\
     1 & 12 \\\\
     \\hline
     \\end{{tabular}}
     \\end{{center}}
   - GENERAL SPACING: Use wide axes (10cm to 12cm) for number and probability lines, stagger labels, and ensure Venn diagrams have separated centers so text never collides. All TikZ code must be clean, 100% syntactically valid LaTeX enclosed in \\begin{{center}}\\begin{{tikzpicture}}...\\end{{tikzpicture}}\\end{{center}}.
   - STRICTLY FORBIDDEN (SET NOTATION): NEVER use university/abstract set theory notation, set builder notation, or abstract set symbols (such as set membership in, not-in, for-all, there-exists, set-builder braces, cardinality bars, subset, union, intersection, or blackboard bold R). High school students at this centre do not understand university set theory. State all definitions, conditions, domain, and range in clear, plain English and standard high school inequalities or intervals (e.g. write 'Each $x$-value has at most one $y$-value', 'For all real $x$', '$x \\ge 0$', 'Domain: all real $x$', 'Vertical Line Test: Any vertical line $x = c$ intersects the graph at most once').

   - STRICTLY FORBIDDEN (SIGMA NOTATION): NEVER use capital sigma summation notation (\\sum, \\Sigma, or ∑). Year 10 NSW students have NOT been taught summation notation! Always write formulas and working in plain English: 'Sum of degrees = 2 × number of edges' or 'Sum of degrees = 2e', 'Sum of scores', etc. Write additions out explicitly (e.g. deg(A) + deg(B) + deg(C) = 2e).

STRICT LATEX RULES:
Every single variable, expression, equation, fraction, or formula MUST be in valid LaTeX enclosed in single dollar signs $...$ (e.g. '$y = mx + b$', '$\\frac{{a}}{{\\sin A}} = \\frac{{b}}{{\\sin B}}$').

CRITICAL JSON ESCAPING:
Inside JSON string values, escape every LaTeX backslash as double backslash (e.g. write '\\\\frac' instead of '\\frac', '\\\\sqrt' instead of '\\sqrt'). Return strictly valid JSON.

OUTPUT FORMAT:
Respond with valid JSON ONLY matching this exact structure:
{{
  "title": "{year_level} Mathematics - {topic} Topic Review & Exam Revision Booklet",
  "year_level": "{year_level}",
  "topic": "{topic}",
  "term": {term if term is not None else "null"},
  "week": {week if week is not None else "null"},
  "textbook": "{textbook}",
  "concepts": [
    {{
      "concept_name": "Exact Name of Subtopic/Concept",
      "revision_summary": "- **What It Is (From Scratch)**: Clear, simple explanation of the concept from first principles in plain English...\\n- **Rule**: Exact mathematical law or relation in simple English and LaTeX...\\n- **Visual Intuition**: How to picture this on a graph or sketch...\\n- **Step-by-Step Method**: 1. First step, 2. Next step, 3. Verify...\\n- **Exam Action Trigger**: Clue or keyword in an exam question...\\n- **Common Trap & Self-Check**: Mistake to avoid and how to self-check...",
      "key_formulas": [
        "Formula 1 with LaTeX ($...$) and variable definitions",
        "Formula 2 with LaTeX ($...$)"
      ],
      "tips_and_tricks": "High-yield examination shortcut, algebraic trick, or tutor secret...",
      "common_pitfalls": [
        "Specific exam trap or common student error 1",
        "Specific exam trap or common student error 2"
      ],
      "tikz_diagram": "\\\\begin{{center}}\\\\begin{{tikzpicture}}...\\\\end{{tikzpicture}}\\\\end{{center}} (or empty string)",
      "mastery_examples": [
        {{
          "example_num": 1,
          "title": "Example Title",
          "problem_text": "Exam-style problem statement with LaTeX...",
          "diagram_tikz": "",
          "solution_diagram_tikz": "",
          "worked_solution": "Full step-by-step model solution with LaTeX...",
          "exam_commentary": "Why this is tested in yearly exams and where marks are lost..."
        }}
      ],
      "review_questions": [
        {{
          "q_num": 1,
          "difficulty": "Level 1 - Commit to Memory",
          "marks": 1,
          "text": "Direct formula/algebraic recall question without diagram...",
          "diagram_tikz": "",
          "solution_diagram_tikz": "",
          "worked_solution": "Step-by-step solution with mark criteria...",
          "final_answer": "Concise final answer in LaTeX..."
        }},
        {{
          "q_num": 2,
          "difficulty": "Level 2 - Further Practice",
          "marks": 2,
          "text": "In the diagram shown below, calculate ... (visual deduction question)",
          "diagram_tikz": "\\\\begin{{center}}\\\\begin{{tikzpicture}}...\\\\end{{tikzpicture}}\\\\end{{center}}",
          "solution_diagram_tikz": "",
          "worked_solution": "Step-by-step solution referencing the diagram...",
          "final_answer": "Concise final answer in LaTeX..."
        }},
        {{
          "q_num": 3,
          "difficulty": "Level 3 - Application",
          "marks": 3,
          "text": "Contextual worded problem or formula calculation without diagram...",
          "diagram_tikz": "",
          "solution_diagram_tikz": "",
          "worked_solution": "Step-by-step solution with mark criteria...",
          "final_answer": "Concise final answer in LaTeX..."
        }},
        {{
          "q_num": 4,
          "difficulty": "Exam Style",
          "marks": 3,
          "text": "Multi-stage exam problem with given diagram shown below...",
          "diagram_tikz": "\\\\begin{{center}}\\\\begin{{tikzpicture}}...\\\\end{{tikzpicture}}\\\\end{{center}}",
          "solution_diagram_tikz": "",
          "worked_solution": "Step-by-step solution with mark criteria...",
          "final_answer": "Concise final answer in LaTeX..."
        }}
      ]
    }}
  ]
}}
"""

    models_to_try = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
    last_err = None

    for model_name in models_to_try:
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
                max_output_tokens=65536
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            raw_text = response.text or ""
            data = clean_json_response(raw_text)

            # Defensive validation
            if not isinstance(data, dict):
                data = {}
            if "concepts" not in data or not isinstance(data["concepts"], list):
                data["concepts"] = []

            # Normalize concept fields
            for c in data.get("concepts", []):
                if "name" not in c and "concept_name" in c:
                    c["name"] = c["concept_name"]
                if "revision_summary" not in c and "theory_content" in c:
                    c["revision_summary"] = c["theory_content"]
                if "key_formulas" not in c:
                    c["key_formulas"] = []
                if "tips_and_tricks" not in c and "tutor_tips" in c:
                    c["tips_and_tricks"] = c["tutor_tips"]
                if "common_pitfalls" not in c:
                    c["common_pitfalls"] = []
                if "mastery_examples" not in c and "teacher_examples" in c:
                    c["mastery_examples"] = c["teacher_examples"]
                if "review_questions" not in c and "practice_questions" in c:
                    c["review_questions"] = c["practice_questions"]
                for q in c.get("review_questions", []):
                    if "difficulty" in q:
                        q["difficulty"] = normalize_difficulty(q["difficulty"])

            data["title"] = f"{year_level} - {topic_str} Topic Review Booklet"
            data["year_level"] = year_level
            data["topic"] = topic_str
            data["term"] = term
            data["week"] = week
            data["textbook"] = textbook
            data["custom_instructions"] = custom_instructions or ""
            data["custom_notes"] = custom_instructions or ""
            data["extra_instructions"] = custom_instructions or ""

            # Assemble marking key for answer sheets and export
            rb_marking_key = {}
            total_rev_q = 1
            for c_idx, c in enumerate(data.get("concepts", []), 1):
                p_let = chr(ord('A') + (c_idx - 1)) if c_idx <= 26 else f"A{c_idx}"
                for q_idx, q in enumerate(c.get("review_questions", []), 1):
                    lbl = str(total_rev_q) if len(data.get("concepts", [])) == 1 else f"{p_let}{q_idx}"
                    rb_marking_key[lbl] = str(q.get("final_answer", "")).strip()
                    total_rev_q += 1
            data["marking_key"] = rb_marking_key

            prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            candidates_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            est_cost = estimate_gemini_cost(prompt_tokens, candidates_tokens, model=model_name)
            data["meta_tokens"] = total_tokens
            data["meta_cost"] = round(est_cost, 5)
            data["model_used"] = model_name
            return audit_and_sanitize_year11_advanced_data(data, year_level, strict=True)
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Review booklet generation failed across models: {last_err}")


def generate_exam_package(
    year_level: str,
    topic: Union[str, List[str]],
    subtopics: Optional[List[str]] = None,
    examples_per_concept: int = 2,
    practice_per_concept: int = 4,
    term: Optional[int] = None,
    week: Optional[int] = None,
    custom_instructions: str = "",
    textbook: str = "CambridgeMATHS NSW",
    api_key: Optional[str] = None,
    question_distribution: Optional[Dict[str, Any]] = None,
    level_distribution: Optional[Dict[str, int]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Generates a Complete Exam Revision & Practice Package for DA Tuition students.
    Combines:
    1. Booklet 1 (Theory & Worked Examples): High-yield anti-textbook study notes,
       Neon UI Exam Hacks/Shortcuts, Coloured Speech Bubble Traps & Pitfalls, and
       Worked Past Paper Examples with full marking guidelines.
    2. Booklet 2 (Exam Practice & Past Papers): Tiered practice questions and authentic
       past-paper style questions, with Student Edition (clean questions + spacious working areas)
       and Complete Solutions & Marking Guidelines Edition.
    """
    client = get_client(api_key)

    if "selected_subtopics" in kwargs and not subtopics:
        subtopics = kwargs["selected_subtopics"]
    if "questions_per_concept" in kwargs and practice_per_concept == 4:
        practice_per_concept = kwargs["questions_per_concept"]
    if "custom_notes" in kwargs and not custom_instructions:
        custom_instructions = kwargs["custom_notes"]
    if "question_distribution" in kwargs and not question_distribution:
        question_distribution = kwargs["question_distribution"]
    if "level_distribution" in kwargs and not level_distribution:
        level_distribution = kwargs["level_distribution"]

    if isinstance(topic, list):
        topic_list = [str(t).strip() for t in topic if str(t).strip()]
        topic_str = format_combined_topics(topic_list)
        is_multi_topic = len(topic_list) > 1
    else:
        topic_list = [str(topic).strip()]
        topic_str = clean_topic_title(str(topic))
        is_multi_topic = False

    if not subtopics:
        subtopics = []
        for t in topic_list:
            try:
                subs = get_curriculum_subtopics(year_level, t, textbook=textbook)
                if is_multi_topic:
                    t_clean = clean_topic_title(t)
                    subtopics.extend([f"[{t_clean}] {s}" for s in subs])
                else:
                    subtopics.extend(subs)
            except Exception:
                subtopics.append(t)
        if not subtopics:
            subtopics = [f"{topic_str} Core Principles", f"{topic_str} Past Paper Mastery"]

    subtopics_bullet_list = "\n".join([f"- {s}" for s in subtopics])

    multi_topic_prompt = ""
    if is_multi_topic:
        multi_topic_prompt = f"- Multi-Topic Package: Consolidates {len(topic_list)} syllabus topics/chapters: {topic_str}. Group study notes, hacks, and questions logically.\n"

    dist_prompt = ""
    practice_spec = f"- Practice Exam Questions per concept: {practice_per_concept} (tiered from Drilling up to Challenging / Past Paper style)\n"
    if question_distribution:
        dist_lines = []
        for sub, tiers in question_distribution.items():
            tier_strs = [f"{tier}: {cnt} question{'s' if cnt != 1 else ''}" for tier, cnt in tiers.items() if cnt > 0]
            if tier_strs:
                dist_lines.append(f"  * For concept \"{sub}\": {', '.join(tier_strs)}")
            else:
                dist_lines.append(f"  * For concept \"{sub}\": 0 practice questions (concept has theory & worked examples only)")
        if dist_lines:
            dist_prompt = "- Exact Question Tier Breakdown Per Subtopic (MANDATORY - generate the EXACT number and tiers of practice questions specified for each individual subtopic):\n" + "\n".join(dist_lines) + "\n"
            practice_spec = "- Practice Exam Questions: Custom question tier distribution configured individually per concept (see exact breakdown below).\n"
    elif level_distribution:
        tier_strs = [f"{tier}: {cnt} question{'s' if cnt != 1 else ''}" for tier, cnt in level_distribution.items() if cnt > 0]
        if tier_strs:
            dist_prompt = f"- Exact Question Tier Breakdown Per Concept (MANDATORY): Each concept must have: {', '.join(tier_strs)}.\n"

    prompt = f"""You are an Elite Senior Mathematics Exam Director and HSC Chief Examiner at DA Tuition in Sydney, Australia.
You are designing a prestigious, publication-quality COMPLETE EXAM REVISION & PRACTICE PACKAGE for {year_level}.

BOOKLET PACKAGE SPECIFICATIONS:
- Year Level: {year_level}
- Target Topic(s): {topic_str}
- Curriculum / Textbook Reference: {textbook}
- Term / Week: {f'Term {term}, Week {week}' if (term and week) else 'Independent Comprehensive Exam Package'}
- Concepts / Subtopics to cover in this package:
{subtopics_bullet_list}
{multi_topic_prompt}- Worked Past Paper Demonstration Examples per concept: {examples_per_concept} (authentic HSC/Trial standard)
{practice_spec}{dist_prompt}{f'- Special Tutor & Exam Instructions: {custom_instructions}' if custom_instructions else ''}

{get_stage6_syllabus_boundary_prompt(year_level, topic_str)}

CRITICAL DESIGN DIRECTIVES (SELF-LEARNING TUITION GUIDE • COMPREHENSIVE & INTUITIVE • ANTI-TEXTBOOK):
1. STUDY NOTES (`study_notes`):
   - DESIGNED FOR COMPLETE INDEPENDENT SELF-LEARNING: The student may NEVER have learned this topic at school before. They must be able to read these notes and understand the entire concept from scratch without requiring a teacher, parent, or tutor to explain it to them.
   - SIMPLE, ACCESSIBLE LANGUAGE (ZERO ACADEMIC FLUFF): Use simple words, intuitive real-world or geometric analogies, and plain English. Avoid dense, intimidating academic jargon. If introducing any mathematical terms (e.g. domain, asymptote, gradient, radicand), define them immediately in plain English so the student feels confident.
   - DETAILED, COMPREHENSIVE & THOROUGH (DO NOT SHORTEN EXCESSIVELY): Provide 4 to 6 detailed, informative, high-yield bullet points in `summary_points` that thoroughly guide the student through the concept from first principles.
   - MANDATORY THEORY VISUALISATION DIAGRAM (`tikz_diagram` in `study_notes`): Every concept must include a clean, compilable, pedagogically rich TikZ diagram illustrating the core visual intuition or geometric representation of the concept (e.g., function vs non-function with vertical line test, domain/range on coordinate axes, parabola with vertex and axis of symmetry, hyperbola with asymptotes). Keep diagram compact (height 3.5cm to 4.5cm).
   - Structured Micro-Headers in `summary_points` (MANDATORY):
     * - **What It Is (From Scratch):** Crystal-clear explanation of the concept from first principles in plain everyday English.
     * - **Rule:** The fundamental mathematical rule or law in simple, plain, easy-to-understand English with clean LaTeX. (MANDATORY: Use label '**Rule:**', NEVER 'The High-Yield Rule').
     * - **Visual Intuition & Mental Picture:** How to visualize this concept in your head or on a Cartesian sketch (e.g. "Think of a vertical asymptote as an invisible electric fence that the curve gets closer and closer to, but is strictly forbidden to touch").
     * - **Step-by-Step Self-Study Guide:** A numbered, foolproof action recipe telling the student exactly what to do when solving these problems. MUST format each step on its own line: '1. [First action] \n 2. [Next step] \n 3. [Final verification]'. Do not merge them into a single line.
     * - **Exam Action Trigger:** What specific clue, phrase, or visual in an exam question triggers this exact method.
     * - **Quick Self-Check Trick:** How the student can independently check their own answer to see if it makes sense without looking at the solutions (e.g., test a simple number like $x=0$, check the sign, or verify endpoints).
   - `essential_formulas`: A comprehensive list of the critical exam formulas with LaTeX, accompanied by a clear, plain-English breakdown of what every single variable, letter, and parameter represents.

2. EXAM HACKS & SHORTCUTS (`exam_hacks`):
   - These are rendered in glowing NEON UI FRAMES in the final PDF!
   - Provide 1-2 high-leverage exam hacks, calculation shortcuts, algebraic time-savers, or calculator tricks (e.g. Casio fx-82AU / fx-100AU tricks, mental parity checks, graphical intuition).
   - Each hack must have `title` and `hack_content`.

3. COMMON EXAM MISTAKES & DEADLY TRAPS (`common_mistakes`):
   - These are rendered in COLOURED SPEECH BUBBLES with callout pointers in the final PDF!
   - Provide 2-3 specific traps where students commonly lose marks (e.g. sign errors in expansion, missing $\\pm$ when square-rooting, division by zero, forgetting domain/range constraints, radian vs degree mode, forgetting to test endpoints).
   - Each trap must have `trap_title` and `trap_explanation`.

4. WORKED PAST PAPER EXAMPLES (`worked_past_paper_examples`):
   - Provide {examples_per_concept} authentic past-paper / trial exam style problems per concept.
   - Provide realistic NSW HSC / School Trial context in `source_tag` (e.g. "HSC Examination Standard", "Selective High Schools Trial Style", "Independent Trials Challenge").
   - State exact marks (e.g. 2, 3, or 4 marks).
   - CRITICAL REQUIREMENT FOR `worked_solution` (LINE-BY-LINE HSC MARKING GUIDELINE LAYOUT):
     * DO NOT clump multiple algebraic steps or equations onto a single paragraph or run-on line!
     * Every equation and deduction must be written line-by-line with generous vertical spacing.
     * DO NOT put markdown bold asterisks around Step headers (write 'Step 1: ...', NOT '**Step 1: ...**').
     * NEVER wrap full English explanatory sentences inside display math \\[ \\text{{...}} \\]! Write English prose outside display math as normal text paragraphs. Only put mathematical equations, formulas, and algebraic derivations inside \\[ ... \\].
     * NEVER start a line with a dangling comma or period (e.g. write 'Therefore, the relation fails...', NEVER '\\n, the relation fails...').
     * Leave a clear blank line before starting Step 2, Step 3, etc.
     * Format each step explicitly:
       Step 1: [Short step name / action]
       \\[ equation 1 \\]

       Step 2: [Next algebraic manipulation]
       \\[ \\begin{{aligned}}
          \\text{{lhs}} &= \\text{{rhs}}_1 \\\\
                     &= \\text{{rhs}}_2
       \\end{{aligned}} \\]
       Therefore, [final conclusion].
     * Match the pristine, spaced-out line-by-line layout of official NSW HSC Marking Guidelines and Senior Marker exemplar solutions.
   - Provide complete, point-by-point `marking_guidelines`: A list of objects `{{"marks": 1, "criteria": "..."}}` explaining exactly how marks are awarded by examiners.
   - Provide `examiner_tip`: High-value insight into marker pet peeves and how to secure full marks.

5. PRACTICE EXAM & PAST PAPER QUESTIONS (`practice_questions`):
   - Provide the exact number and tier of practice questions specified in the Question Tier Breakdown for each concept (or exactly {practice_per_concept} questions per concept if no custom breakdown).
   - Tier difficulty progressively across:
      * Section 1 - Commit to Memory (1-2 marks): Foundational calculation or definition recall.
      * Section 2 - Further Practice (2-3 marks): Multi-step standard exam procedure.
      * Section 3 - Application (2-4 marks): Applied context, geometry, or worded scenario.
      * Section 4 - Thinking Creatively (3-5 marks): Multi-stage synthesis, distinction challenge.
      * Section 5 - Exam Questions (3-5 marks): Authentic past-paper trial question, multi-part synthesis, or rigorous proof.
   - Set `difficulty` strictly to one of the 5 Section tier names above (use 'Section', NEVER 'Level').
   - Set `source_tag` (e.g. "Foundational Drill", "Standard Exam Question", "Past HSC Standard", "School Trial Synthesiser").
   - Allocate marks (1 to 5 marks).
   - Include complete line-by-line `worked_solution` in official HSC marking guideline format with displayed equations.
   - Include clear point-by-point `marking_guidelines` with mark breakdowns.
   - Include concise `final_answer` in LaTeX for fast verification.
   - Include `examiner_pitfall`: The single most common mistake made by candidates on this specific question.
   - Include `working_lines_cm`: Recommended height in cm for student working space (e.g. 4.5 for 2 marks, 5.5 for 3 marks, 7.0 for 4-5 marks).

6. DIAGRAMS & TIKZ GRAPH SCALING RULES (CRITICAL):
   - MANDATORY QUESTION VARIETY: BALANCED MIX OF DIAGRAM & NON-DIAGRAM QUESTIONS:
     * To reflect authentic examination variety, practice questions must feature a healthy, balanced mix:
     * In visual, geometric, network, graph, trigonometry, coordinate geometry, or measurement topics:
       - Approximately 40% to 60% of practice questions MUST be visual interpretation questions with a complete given TikZ diagram provided in `diagram_tikz`.
       - The remaining ~40% to 60% of practice questions MUST be non-diagram questions (purely algebraic drills, calculation from formula, or worded problems where `diagram_tikz` is empty `""`).
     * NEVER return a practice question set where 100% of questions have no diagrams!
     * NEVER return a practice question set where all questions are identical in structure! Ensure authentic variety!
   - MANDATORY GIVEN DIAGRAMS FOR STUDENTS (HSC / NSW EXAM STANDARD):
     * Students must always be GIVEN diagrams for questions involving networks, graph theory, shortest paths, planar graphs, minimum spanning trees, geometry, bearings, angles of elevation/depression, or trigonometry, unless the question explicitly awards marks for constructing/drawing the diagram.
     * NEVER describe network vertices and edge weights or geometric configurations solely in text without providing the compilable LaTeX TikZ diagram in `diagram_tikz`. In NSW examinations, students are supplied with the visual diagram.
   - For any geometry, trigonometry, vectors, curve sketching, or statistics question, provide compilable TikZ code in `diagram_tikz` and/or `solution_diagram_tikz`.
   - TikZ must be 100% syntactically clean LaTeX enclosed in \\begin{{center}}\\begin{{tikzpicture}}...\\end{{tikzpicture}}\\end{{center}}.
   - VERTICAL LINE TEST TIKZ RULES:
     * NEVER place the vertical test line along the y-axis ($x = 0$)! Always offset the vertical test line to $x = 1$ or $x = 2$ where it intersects the curve clearly.
     * For the test line label, place it with `node[above=3pt, red, fill=none, inner sep=1.5pt] {{$x = 1$}};` and keep it clear of axis arrow tips and labels.
     * Ensure the y-axis is clearly labeled with `node[above left] {{$y$}}` and x-axis with `node[right] {{$x$}}`.
   - GRAPH SCALING RULES:
     * For all function graphs, parabolas, cubics, quartics, hyperbolas, and circles, ALWAYS BALANCE AXIS SCALING on \\begin{{tikzpicture}}[x=...cm, y=...cm]:
       - If the y-values span large numbers (e.g. y from -15 to +15), YOU MUST SCALE THE Y-AXIS APPROPRIATELY, e.g. \\begin{{tikzpicture}}[x=0.8cm, y=0.22cm], so the total graph height NEVER exceeds 5.2cm!
       - NEVER use default 1cm:1cm scaling when the y-values span more than 6 units (e.g. y from -12 to 8 with 1cm=1unit produces an absurd 20cm needle graph that ruins the page!).
       - Keep total diagram width between 6.0cm and 8.5cm, and total diagram height between 4.0cm and 5.2cm.
     * PREVENT ASYMPTOTE BLOWUPS: For hyperbolas and curves with asymptotes, use \\clip or domain restrictions so curves do not shoot off to infinity.
     * LABEL COLLISION PREVENTION: Never place two labels with identical anchors near the origin. Use contrasting anchors (e.g. node[above right] vs node[below left]), transparent label backgrounds (`fill=none`), and enough spacing that text never overlaps.

STRICT LATEX & JSON FORMATTING:
- Enclose all mathematical variables, expressions, and equations in single dollar signs $...$ (e.g. '$y = mx + b$', '$\\vec{{v}} = 3\\mathbf{{i}} - 4\\mathbf{{j}}$').
- In JSON, escape all backslashes as double backslashes (e.g. '\\\\frac', '\\\\sqrt').
- Return strictly valid JSON ONLY.

OUTPUT SCHEMA:
{{
  "title": "{year_level} Mathematics - {topic_str} Complete Exam Package",
  "year_level": "{year_level}",
  "topic": "{topic_str}",
  "textbook": "{textbook}",
  "term": {term if term is not None else "null"},
  "week": {week if week is not None else "null"},
  "concepts": [
    {{
      "concept_name": "Name of Concept / Subtopic",
      "study_notes": {{
        "tikz_diagram": "\\begin{{center}}\\begin{{tikzpicture}}...\\end{{tikzpicture}}\\end{{center}}",
        "summary_points": [
          "- **What It Is (From Scratch):** Crystal-clear explanation of the concept from first principles in plain English...",
          "- **Rule:** Fundamental mathematical rule in simple, easy-to-understand English with LaTeX...",
          "- **Visual Intuition & Mental Picture:** How to visualize this on a sketch or in your head...",
          "- **Step-by-Step Self-Study Guide:** 1. First... \\n 2. Next... \\n 3. Finally...",
          "- **Exam Action Trigger**: Specific clue or keyword in an exam question...",
          "- **Quick Self-Check Trick**: Test a simple value..."
        ],
        "essential_formulas": [
          {{"name": "Formula Name", "formula": "$...$", "note": "Plain-English description of variables and when to apply"}}
        ]
      }},
      "exam_hacks": [
        {{
          "title": "Hack Title",
          "hack_content": "Concrete shortcut or calculator technique..."
        }}
      ],
      "common_mistakes": [
        {{
          "trap_title": "Deadly Trap Title",
          "trap_explanation": "Specific trap explanation and how to avoid losing marks..."
        }}
      ],
      "worked_past_paper_examples": [
        {{
          "example_num": 1,
          "title": "Example Title",
          "source_tag": "HSC Examination Standard",
          "marks": 3,
          "problem_text": "Problem statement with LaTeX...",
          "diagram_tikz": "",
          "solution_diagram_tikz": "",
          "worked_solution": "**Step 1: Title**\\n\\[ equation \\]\\n**Step 2: Title**\\n\\[ equation \\]",
          "marking_guidelines": [
            {{"marks": 1, "criteria": "Applies correct formula..."}},
            {{"marks": 1, "criteria": "Substitutes values correctly..."}},
            {{"marks": 1, "criteria": "Calculates final exact value..."}}
          ],
          "examiner_tip": "Advice on common deductions..."
        }}
      ],
      "practice_questions": [
        {{
          "q_num": 1,
          "source_tag": "Direct Calculation",
          "difficulty": "Section 1 - Commit to Memory",
          "marks": 2,
          "text": "Direct formula evaluation or algebraic calculation without diagram...",
          "diagram_tikz": "",
          "solution_diagram_tikz": "",
          "worked_solution": "**Step 1: Formula Selection**\\n\\[ equation \\]\\n**Step 2: Substitution & Evaluation**\\n\\[ equation \\]",
          "marking_guidelines": [
            {{"marks": 1, "criteria": "States correct formula and substitutes..."}},
            {{"marks": 1, "criteria": "Evaluates exact numerical answer..."}}
          ],
          "final_answer": "Concise answer...",
          "examiner_pitfall": "Specific error to watch out for...",
          "working_lines_cm": 4.5
        }},
        {{
          "q_num": 2,
          "source_tag": "Authentic Past Paper Style",
          "difficulty": "Section 2 - Further Practice",
          "marks": 3,
          "text": "In the diagram shown below, ... (visual interpretation question)",
          "diagram_tikz": "\\\\begin{{center}}\\\\begin{{tikzpicture}}...\\\\end{{tikzpicture}}\\\\end{{center}}",
          "solution_diagram_tikz": "",
          "worked_solution": "**Step 1: Geometric/Network Deduction**\\n\\[ equation \\]\\n**Step 2: Final Calculation**\\n\\[ equation \\]",
          "marking_guidelines": [
            {{"marks": 1, "criteria": "Interprets visual diagram correctly..."}},
            {{"marks": 1, "criteria": "Sets up mathematical equation..."}},
            {{"marks": 1, "criteria": "Calculates final value..."}}
          ],
          "final_answer": "Concise answer...",
          "examiner_pitfall": "Specific error to watch out for...",
          "working_lines_cm": 5.5
        }}
      ]
    }}
  ]
}}
"""

    models_to_try = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
    last_err = None

    for model_name in models_to_try:
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
                max_output_tokens=65536
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            raw_text = response.text or ""
            data = clean_json_response(raw_text)

            if not isinstance(data, dict):
                data = {}
            if "concepts" not in data or not isinstance(data["concepts"], list):
                data["concepts"] = []

            # Defensive normalization of concept fields
            total_examples = 0
            total_questions = 0
            total_marks = 0
            marking_key = {}
            q_global_idx = 1

            for c_idx, c in enumerate(data.get("concepts", []), 1):
                p_let = chr(ord('A') + (c_idx - 1)) if c_idx <= 26 else f"A{c_idx}"
                if "name" not in c and "concept_name" in c:
                    c["name"] = c["concept_name"]
                if "concept_name" not in c and "name" in c:
                    c["concept_name"] = c["name"]

                # Study notes normalization
                if "study_notes" not in c or not isinstance(c["study_notes"], dict):
                    c["study_notes"] = {
                        "summary_points": c.get("summary_points") or [c.get("revision_summary", "Core concept review")],
                        "essential_formulas": c.get("essential_formulas") or c.get("key_formulas", []),
                        "tikz_diagram": c.get("tikz_diagram", "")
                    }
                elif "tikz_diagram" in c and not c["study_notes"].get("tikz_diagram"):
                    c["study_notes"]["tikz_diagram"] = c["tikz_diagram"]

                # Hacks & Mistakes normalization
                if "exam_hacks" not in c or not isinstance(c["exam_hacks"], list):
                    if c.get("tips_and_tricks"):
                        c["exam_hacks"] = [{"title": "Tutor Shortcut", "hack_content": str(c["tips_and_tricks"])}]
                    else:
                        c["exam_hacks"] = []

                if "common_mistakes" not in c or not isinstance(c["common_mistakes"], list):
                    if c.get("common_pitfalls"):
                        c["common_mistakes"] = [{"trap_title": "Exam Trap", "trap_explanation": str(p)} for p in c["common_pitfalls"]]
                    else:
                        c["common_mistakes"] = []

                # Worked past paper examples normalization
                exs = c.get("worked_past_paper_examples") or c.get("mastery_examples") or c.get("teacher_examples") or []
                c["worked_past_paper_examples"] = exs
                total_examples += len(exs)

                # Practice questions normalization
                pqs = c.get("practice_questions") or c.get("review_questions") or []
                for q_idx, q in enumerate(pqs, 1):
                    if "difficulty" in q:
                        q["difficulty"] = normalize_difficulty(q["difficulty"])
                    m_val = q.get("marks", 2)
                    try:
                        m_int = int(m_val)
                    except Exception:
                        m_int = 2
                    q["marks"] = m_int
                    total_marks += m_int

                    lbl = str(q_global_idx) if len(data["concepts"]) == 1 else f"{p_let}{q_idx}"
                    marking_key[lbl] = str(q.get("final_answer", "")).strip()
                    q_global_idx += 1

                c["practice_questions"] = pqs
                total_questions += len(pqs)

            data["title"] = f"{year_level} - {topic_str} Complete Exam Package"
            data["year_level"] = year_level
            data["topic"] = topic_str
            data["term"] = term
            data["week"] = week
            data["textbook"] = textbook
            data["custom_instructions"] = custom_instructions or ""
            data["total_examples"] = total_examples
            data["total_questions"] = total_questions
            data["total_marks"] = total_marks
            data["marking_key"] = marking_key

            prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            candidates_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            est_cost = estimate_gemini_cost(prompt_tokens, candidates_tokens, model=model_name)
            data["meta_tokens"] = total_tokens
            data["meta_cost"] = round(est_cost, 5)
            data["model_used"] = model_name
            return audit_and_sanitize_year11_advanced_data(data, year_level, strict=True)

        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Exam package generation failed across models: {last_err}")


USD_TO_AUD_RATE = 1.55


def estimate_gemini_cost(prompt_tokens: int, candidates_tokens: int = 0, model: str = "gemini-3.8-flash", currency: str = "AUD") -> float:
    """
    Estimates generation cost in AUD (or USD) based on official Gemini token pricing and AUD FX rate.
    - Gemini 3.8 / 3.7 Flash: $0.75 / 1M input tokens, $3.75 / 1M output tokens (USD)
    - Gemini 3.5 Flash: $0.35 / 1M input tokens, $1.05 / 1M output tokens (USD)
    - Gemini 2.5 Flash: $0.30 / 1M input tokens, $2.50 / 1M output tokens (USD)
    - Gemini 2.5 Flash-Lite: $0.10 / 1M input tokens, $0.40 / 1M output tokens (USD)
    - Gemini 2.0 Flash: $0.10 / 1M input tokens, $0.40 / 1M output tokens (USD)
    - Gemini 1.5 Flash: $0.075 / 1M input tokens, $0.30 / 1M output tokens (USD)
    - Gemini Pro: $1.25 / 1M input tokens, $5.00 / 1M output tokens (USD)
    - USD to AUD conversion rate: 1.55
    """
    model_lower = str(model).lower()
    if "flash-lite" in model_lower or "lite" in model_lower:
        cost = ((prompt_tokens / 1_000_000) * 0.10) + ((candidates_tokens / 1_000_000) * 0.40)
    elif "3.8" in model_lower or "3.7" in model_lower:
        cost = ((prompt_tokens / 1_000_000) * 0.75) + ((candidates_tokens / 1_000_000) * 3.75)
    elif "3.5" in model_lower:
        cost = ((prompt_tokens / 1_000_000) * 0.35) + ((candidates_tokens / 1_000_000) * 1.05)
    elif "2.5" in model_lower:
        cost = ((prompt_tokens / 1_000_000) * 0.30) + ((candidates_tokens / 1_000_000) * 2.50)
    elif "2.0" in model_lower:
        cost = ((prompt_tokens / 1_000_000) * 0.10) + ((candidates_tokens / 1_000_000) * 0.40)
    elif "1.5" in model_lower:
        cost = ((prompt_tokens / 1_000_000) * 0.075) + ((candidates_tokens / 1_000_000) * 0.30)
    elif "pro" in model_lower:
        cost = ((prompt_tokens / 1_000_000) * 1.25) + ((candidates_tokens / 1_000_000) * 5.00)
    else:
        # Default fallback to gemini-3.8-flash pricing
        cost = ((prompt_tokens / 1_000_000) * 0.75) + ((candidates_tokens / 1_000_000) * 3.75)

    if currency.upper() == "AUD":
        return round(cost * USD_TO_AUD_RATE, 5)
    return round(cost, 5)


# Module-level aliases for backwards-compatibility
generate_topic_review_booklet = generate_review_booklet
generate_complete_exam_package = generate_exam_package
