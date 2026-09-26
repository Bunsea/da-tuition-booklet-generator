"""
NSW Mathematics Curriculum Data for Years 7 to 10.
Aligned with the NSW NESA Mathematics Syllabus across major textbooks:
- New Century Maths (Nelson Cengage)
- Jacaranda Maths Quest (Wiley)
- Australian Signpost Mathematics (Pearson)
- Oxford Maths NSW (Oxford University Press)
- Mathscape (Macmillan)
"""

from typing import Dict, List

# ==============================================================================
# 1. NEW CENTURY MATHS (NELSON CENGAGE) - NSW 7-10 SYLLABUS
# ==============================================================================
NEW_CENTURY_CURRICULUM: Dict[str, Dict[str, List[str]]] = {
    "Year 7": {
        "1. Integers": [
            "1.1 Understanding negative numbers and the number line",
            "1.2 Adding and subtracting directed numbers",
            "1.3 Multiplying and dividing integers",
            "1.4 Order of operations with integers (BODMAS)",
            "1.5 Practical problem solving with directed numbers"
        ],
        "2. Angles": [
            "2.1 Naming and measuring angles with a protractor",
            "2.2 Classifying acute, obtuse, right, reflex and straight angles",
            "2.3 Complementary and supplementary angles",
            "2.4 Angles at a point and vertically opposite angles",
            "2.5 Angles on parallel lines: alternate, corresponding and co-interior",
            "2.6 Angle sum of a triangle and quadrilateral"
        ],
        "3. Whole Numbers and Divisibility": [
            "3.1 Place value, rounding and estimation",
            "3.2 Prime and composite numbers",
            "3.3 Divisibility tests (2, 3, 4, 5, 6, 8, 9, 10)",
            "3.4 Prime factorisation trees and index form",
            "3.5 Highest Common Factor (HCF) and Lowest Common Multiple (LCM)",
            "3.6 Squares, square roots, cubes and cube roots"
        ],
        "4. Fractions and Percentages": [
            "4.1 Equivalent fractions and simplest form",
            "4.2 Proper, improper fractions and mixed numerals",
            "4.3 Adding and subtracting fractions with like and unlike denominators",
            "4.4 Multiplying and dividing fractions and reciprocals",
            "4.5 Converting between fractions and percentages",
            "4.6 Finding a percentage of a quantity",
            "4.7 Percentage increase, decrease and discounts"
        ],
        "5. Algebra and Equations": [
            "5.1 Pronumerals, terms, coefficients and constants",
            "5.2 Translating word problems into algebraic expressions",
            "5.3 Evaluating expressions by substitution",
            "5.4 Collecting like terms (addition and subtraction)",
            "5.5 Multiplying and dividing algebraic terms",
            "5.6 Expanding single brackets using the distributive law",
            "5.7 Solving one-step and two-step linear equations"
        ],
        "6. Geometrical Figures": [
            "6.1 Classifying triangles by side lengths and angles",
            "6.2 Properties of special quadrilaterals (parallelograms, rhombuses, trapezia, kites)",
            "6.3 Polygons and their symmetry properties",
            "6.4 Congruent shapes and identifying matching sides/angles",
            "6.5 Reflections, rotations and translations in the plane"
        ],
        "7. Decimals": [
            "7.1 Decimal place value, ordering and comparisons",
            "7.2 Rounding decimals and significant figures",
            "7.3 Adding and subtracting decimal numbers",
            "7.4 Multiplying and dividing decimals by powers of 10 and whole numbers",
            "7.5 Converting fractions to decimals and decimals to fractions",
            "7.6 Terminating and recurring decimals"
        ],
        "8. Area, Perimeter and Volume": [
            "8.1 Metric units of length and perimeter of plane figures",
            "8.2 Circumference of circles and perimeter of sectors",
            "8.3 Area of squares, rectangles, triangles and parallelograms",
            "8.4 Area of rhombuses, kites and trapeziums",
            "8.5 Area of circles and composite 2D shapes",
            "8.6 Volume and capacity of rectangular prisms"
        ],
        "9. The Number Plane": [
            "9.1 The Cartesian plane, axes, origin and four quadrants",
            "9.2 Plotting and reading ordered pairs (x, y)",
            "9.3 Generating tables of values from linear rules",
            "9.4 Graphing linear relationships on the number plane",
            "9.5 Interpreting practical travel and conversion graphs"
        ],
        "10. Analysing Data": [
            "10.1 Categorical vs numerical data (discrete and continuous)",
            "10.2 Frequency distribution tables and tallying",
            "10.3 Column graphs, histograms and dot plots",
            "10.4 Stem-and-leaf plots",
            "10.5 Measures of center: mean, median and mode",
            "10.6 Measure of spread: range and identifying outliers"
        ],
        "11. Probability": [
            "11.1 The probability scale (0 to 1) and chance terminology",
            "11.2 Theoretical probability of equally likely outcomes",
            "11.3 Complementary events: P(not A) = 1 - P(A)",
            "11.4 Experimental probability and relative frequency",
            "11.5 Sample space representation: lists, tables and tree diagrams"
        ],
        "12. Ratios, Rates and Time": [
            "12.1 Writing and simplifying ratios",
            "12.2 Dividing an amount in a given ratio",
            "12.3 Scale drawings and map ratios",
            "12.4 Rates and unit rates (speed, fuel consumption, hourly wage)",
            "12.5 Time conversions, 12-hour and 24-hour time",
            "12.6 Interpreting bus, train and airline timetables"
        ]
    },
    "Year 8": {
        "1. Pythagoras' Theorem": [
            "1.1 Right-angled triangles and identifying the hypotenuse",
            "1.2 Pythagoras' Theorem rule: c^2 = a^2 + b^2",
            "1.3 Calculating the length of the hypotenuse",
            "1.4 Calculating the length of a shorter side",
            "1.5 Pythagorean triads and verifying right-angled triangles",
            "1.6 Solving real-world 2D practical problems"
        ],
        "2. Working with Numbers": [
            "2.1 Real numbers: rational and irrational numbers",
            "2.2 Index laws for multiplication and division: a^m * a^n and a^m / a^n",
            "2.3 The zero index: a^0 = 1 and power of a power: (a^m)^n",
            "2.4 Expressing large numbers in scientific notation",
            "2.5 Combined operations with indices and order of operations"
        ],
        "3. Algebraic Techniques": [
            "3.1 Simplifying algebraic expressions with powers and fractions",
            "3.2 Multiplying and dividing terms with indices",
            "3.3 Expanding single brackets using the distributive law",
            "3.4 Expanding and collecting like terms",
            "3.5 Factorising algebraic expressions by taking out the HCF",
            "3.6 Simplifying algebraic fractions with numerical denominators"
        ],
        "4. Geometry and Proof": [
            "4.1 Parallel lines and angle relationship proofs",
            "4.2 Angle sum and exterior angle theorem of triangles",
            "4.3 Angle sum of quadrilaterals and n-sided polygons",
            "4.4 Congruent triangle tests: SSS, SAS, AAS, RHS",
            "4.5 Setting up formal geometric congruence proofs"
        ],
        "5. Area, Surface Area and Volume": [
            "5.1 Perimeter of composite shapes and sectors",
            "5.2 Area of composite shapes and shaded regions",
            "5.3 Surface area of cubes, rectangular prisms and triangular prisms",
            "5.4 Volume of right prisms (V = Ah)",
            "5.5 Capacity units and metric conversions (cm^3 to mL, m^3 to L)"
        ],
        "6. Fractions, Percentages and Money": [
            "6.1 Fraction arithmetic and order of operations",
            "6.2 Finding the original amount given a percentage increase or decrease",
            "6.3 Profit, loss and percentage profit/loss",
            "6.4 Simple interest formula: I = Prt",
            "6.5 Calculating principal, interest rate or time period"
        ],
        "7. Investigating Data": [
            "7.1 Grouped frequency distribution tables",
            "7.2 Grouped data histograms and frequency polygons",
            "7.3 Finding the modal class and estimated mean of grouped data",
            "7.4 Comparing data sets using mean, median, mode and range",
            "7.5 Analysing the effect of outliers on data sets"
        ],
        "8. Probability and Multi-Step Experiments": [
            "8.1 Sample space representations for two-step experiments",
            "8.2 Probability tree diagrams with and without replacement",
            "8.3 Venn diagrams and sets (union and intersection)",
            "8.4 Two-way tables and calculating joint probabilities",
            "8.5 The addition rule for mutually exclusive and non-mutually exclusive events"
        ],
        "9. Linear Equations and Inequalities": [
            "9.1 Solving multi-step linear equations",
            "9.2 Equations with pronumerals on both sides",
            "9.3 Equations with brackets and parentheses",
            "9.4 Equations containing algebraic fractions",
            "9.5 Formulating equations to solve word problems",
            "9.6 Graphing and solving linear inequalities on a number line"
        ],
        "10. Ratios, Rates and Speed": [
            "10.1 Constant speed and average speed calculations",
            "10.2 Converting speed units (km/h to m/s and vice versa)",
            "10.3 Unit pricing, supermarket comparisons and best buys",
            "10.4 Direct proportion and constant of proportionality",
            "10.5 Travel graphs: distance-time graphs and gradient as speed"
        ],
        "11. Graphing Linear Equations": [
            "11.1 The linear function form: y = mx + c",
            "11.2 Finding the gradient from a graph using rise over run",
            "11.3 Calculating gradient using the two-point formula: m = (y2 - y1) / (x2 - x1)",
            "11.4 Finding the x-intercept and y-intercept",
            "11.5 Graphing straight lines using table of values and intercept method",
            "11.6 Horizontal lines (y = c) and vertical lines (x = k)"
        ],
        "12. Similar Figures and Cylinders": [
            "12.1 Conditions for similarity and calculating scale factors",
            "12.2 Similar triangle tests (AAA, SAS, SSS, RHS)",
            "12.3 Finding unknown lengths in similar triangles",
            "12.4 Surface area of right cylinders: SA = 2*pi*r^2 + 2*pi*r*h",
            "12.5 Volume of right cylinders: V = pi*r^2*h"
        ]
    },
    "Year 9": {
        "1. Financial Mathematics": [
            "1.1 Earning wages, salaries, overtime and penalty rates",
            "1.2 Piecework, commission and royalties",
            "1.3 Allowances, bonuses and deductions",
            "1.4 Calculating taxable income, PAYG tax and Medicare levy",
            "1.5 Simple interest loans and flat rate investments",
            "1.6 Compound interest using step-by-step tables and formula: A = P(1 + r)^n"
        ],
        "2. Algebraic Techniques and Indices": [
            "2.1 Index laws review for multiplication, division and power of a power",
            "2.2 Negative indices: a^(-n) = 1 / a^n",
            "2.3 Scientific notation for very small and very large numbers",
            "2.4 Expanding binomial products: (a + b)(c + d)",
            "2.5 Factorising algebraic expressions by grouping in pairs",
            "2.6 Simplifying and operating with algebraic fractions"
        ],
        "3. Linear Equations and Inequalities": [
            "3.1 Solving multi-step linear equations with brackets",
            "3.2 Solving equations with algebraic fractions on both sides",
            "3.3 Solving linear inequalities and reversing inequality signs",
            "3.4 Rearranging and transposing formulas",
            "3.5 Formulating equations to solve practical word problems"
        ],
        "4. Pythagoras and Right-Angled Trigonometry": [
            "4.1 Pythagoras' theorem in 2D composite figures",
            "4.2 Naming sides in right triangles: opposite, adjacent, hypotenuse",
            "4.3 The trigonometric ratios: sin, cos, tan (SOH CAH TOA)",
            "4.4 Calculating unknown side lengths in right triangles",
            "4.5 Calculating unknown angles using inverse trigonometric functions",
            "4.6 Angles of elevation and depression",
            "4.7 Three-figure true bearings and compass bearings"
        ],
        "5. Coordinate Geometry and Linear Relationships": [
            "5.1 Calculating distance between two points on the Cartesian plane",
            "5.2 Finding the midpoint of a line segment",
            "5.3 Gradient of a line segment: m = (y2 - y1) / (x2 - x1)",
            "5.4 Equation of a line in gradient-intercept form: y = mx + b",
            "5.5 Finding the equation of a line using point-gradient formula",
            "5.6 Parallel and perpendicular lines and their gradients"
        ],
        "6. Surface Area and Volume": [
            "6.1 Area of composite 2D shapes and circles",
            "6.2 Surface area of right prisms and cylinders",
            "6.3 Volume of right prisms and cylinders",
            "6.4 Surface area of pyramids and cones",
            "6.5 Volume of pyramids, cones and spheres"
        ],
        "7. Geometry and Networks": [
            "7.1 Angle theorems and proofs in geometric figures",
            "7.2 Formal triangle congruence and similarity proofs",
            "7.3 Introduction to networks: vertices, edges, loops and multiple edges",
            "7.4 Degree of a vertex and the Handshaking Lemma",
            "7.5 Traversable networks, Eulerian and Hamiltonian paths/circuits",
            "7.6 Minimum spanning trees and Prim's algorithm"
        ],
        "8. Probability and Bivariate Data": [
            "8.1 Multi-stage probability tree diagrams and arrays",
            "8.2 Dependent and independent events without replacement",
            "8.3 Conditional probability in two-way tables and Venn diagrams",
            "8.4 Five-number summary, quartiles and interquartile range (IQR)",
            "8.5 Constructing and interpreting box plots and detecting outliers",
            "8.6 Scatter plots, trend lines and informal correlation"
        ],
        "9. Surds and Quadratic Expressions (Advanced)": [
            "9.1 Fractional indices and radical notation: a^(1/n) = sqrt[n](a)",
            "9.2 Simplifying surds and extracting perfect squares",
            "9.3 Adding, subtracting, multiplying and dividing surds",
            "9.4 Expanding brackets with surds and rationalising denominators",
            "9.5 Expanding special products: (a +/- b)^2 and (a - b)(a + b)",
            "9.6 Factorising monic quadratic trinomials: x^2 + bx + c",
            "9.7 Factorising non-monic quadratic trinomials: ax^2 + bx + c",
            "9.8 Solving quadratic equations using the null factor law and quadratic formula"
        ],
        "10. Non-Linear Functions and Graphs (Advanced)": [
            "10.1 Graphing parabolas: y = ax^2 + c and finding the vertex",
            "10.2 Features of parabolas: axis of symmetry and intercepts",
            "10.3 Graphing hyperbolas: y = k / x and identifying asymptotes",
            "10.4 Graphing circles centered at origin: x^2 + y^2 = r^2",
            "10.5 Graphing exponential growth and decay curves: y = a^x"
        ]
    },
    "Year 10": {
        "1. Financial Mathematics and Depreciation": [
            "1.1 Compound interest formula: A = P(1 + r)^n",
            "1.2 Calculating compound interest for fractional compounding periods",
            "1.3 Straight-line and declining-balance depreciation",
            "1.4 Credit cards, personal loans, compound interest repayments",
            "1.5 Comparing investment options and superannuation basics"
        ],
        "2. Linear Relationships and Systems": [
            "2.1 Gradient-intercept and general form of a straight line: Ax + By + C = 0",
            "2.2 Parallel lines (m1 = m2) and perpendicular lines (m1 * m2 = -1)",
            "2.3 Solving simultaneous linear equations graphically",
            "2.4 Solving simultaneous equations using algebraic substitution",
            "2.5 Solving simultaneous equations using algebraic elimination",
            "2.6 Real-world applications and break-even analysis"
        ],
        "3. Surface Area and Volume of Complex Solids": [
            "3.1 Surface area of right and oblique pyramids",
            "3.2 Surface area of right cones and spheres",
            "3.3 Volume of composite solids combining prisms, cylinders and cones",
            "3.4 Surface area and volume of spheres and hemispheres",
            "3.5 Errors in measurement, absolute error, percentage error and limits of accuracy"
        ],
        "4. Advanced Trigonometry": [
            "4.1 Right-angled trigonometry applications in 2D and 3D",
            "4.2 Compass and true bearings in navigational multi-step problems",
            "4.3 Trigonometric ratios for angles from 0 to 360 degrees (ASTC rule)",
            "4.4 The Sine Rule for finding sides and angles",
            "4.5 The ambiguous case of the Sine Rule",
            "4.6 The Cosine Rule for finding sides and angles",
            "4.7 Area of a non-right-angled triangle: Area = 1/2 * a * b * sin(C)"
        ],
        "5. Geometry and Network Optimisation": [
            "5.1 Deductive geometric proofs for parallel lines and triangles",
            "5.2 Planar graphs, faces and Euler's formula for networks: v - e + f = 2",
            "5.3 Weighted networks, shortest path problems and Dijkstra's algorithm",
            "5.4 Minimum spanning trees and Kruskal's/Prim's algorithms",
            "5.5 Critical path analysis: activity networks, float times and critical path"
        ],
        "6. Bivariate Statistics and Correlation": [
            "6.1 Investigating bivariate numerical data using scatter plots",
            "6.2 Correlation coefficient r (direction and strength)",
            "6.3 Drawing and calculating the line of best fit",
            "6.4 Making predictions: interpolation vs extrapolation",
            "6.5 Distinguishing correlation from causation and confounding variables",
            "6.6 Standard deviation and normal distributions intro"
        ],
        "7. Multi-Stage Probability": [
            "7.1 Probability tree diagrams for independent and dependent events",
            "7.2 Conditional probability: P(A|B) = P(A and B) / P(B)",
            "7.3 Venn diagrams with three sets and calculating intersections",
            "7.4 Two-way tables and medical/testing false positive problems"
        ],
        "8. Surds, Indices and Logarithms (Advanced)": [
            "8.1 Negative and fractional indices review",
            "8.2 Advanced surd operations and binomial rationalisation",
            "8.3 Definition of a logarithm: y = a^x <=> x = log_a(y)",
            "8.4 Laws of logarithms: product, quotient and power laws",
            "8.5 The change of base rule and evaluating logarithms on a calculator",
            "8.6 Solving exponential equations using logarithms"
        ],
        "9. Quadratic Equations and Parabolic Functions (Advanced)": [
            "9.1 Factorising non-monic quadratics: ax^2 + bx + c",
            "9.2 Solving quadratics by completing the square and quadratic formula",
            "9.3 The discriminant Delta = b^2 - 4ac and nature of roots",
            "9.4 Parabola vertex form: y = a(x - h)^2 + k and transformations",
            "9.5 Maximum and minimum quadratic optimization word problems",
            "9.6 Simultaneous equations involving one linear and one quadratic equation"
        ],
        "10. Polynomials and Function Relations (Advanced)": [
            "10.1 Concept of a mathematical function and the vertical line test",
            "10.2 Domain and range of algebraic functions and relations",
            "10.3 Polynomial definitions, degree, leading term and addition/multiplication",
            "10.4 Polynomial long division and synthetic division",
            "10.5 The Remainder Theorem and Factor Theorem",
            "10.6 Graphing cubic functions and identifying real roots/inflections"
        ],
        "11. Circle Geometry (Advanced)": [
            "11.1 Circle terminology: chords, arcs, sectors, tangents and secants",
            "11.2 Chord theorems: perpendicular bisector from centre to chord",
            "11.3 Angle at centre is twice the angle at the circumference",
            "11.4 Angles in the same segment are equal; angle in a semicircle is 90 degrees",
            "11.5 Cyclic quadrilaterals: opposite angles are supplementary",
            "11.6 Tangents from an external point and radius perpendicular to tangent",
            "11.7 The Alternate Segment Theorem"
        ]
    }
}

NEW_CENTURY_CURRICULUM["Year 9 (Standard)"] = NEW_CENTURY_CURRICULUM["Year 9"]
NEW_CENTURY_CURRICULUM["Year 9 (Advanced)"] = NEW_CENTURY_CURRICULUM["Year 9"]
NEW_CENTURY_CURRICULUM["Year 10 (Standard)"] = NEW_CENTURY_CURRICULUM["Year 10"]
NEW_CENTURY_CURRICULUM["Year 10 (Advanced)"] = NEW_CENTURY_CURRICULUM["Year 10"]


# ==============================================================================
# 2. JACARANDA MATHS QUEST (WILEY) - NSW 7-10 SYLLABUS (learnON)
# ==============================================================================
MATHS_QUEST_CURRICULUM: Dict[str, Dict[str, List[str]]] = {
    "Year 7": {
        "1. Computation with Integers": [
            "1.1 Place value and operations with positive whole numbers",
            "1.2 Directed numbers on the number line",
            "1.3 Addition and subtraction of integers",
            "1.4 Multiplication and division of integers",
            "1.5 Order of operations and grouping symbols (BODMAS)"
        ],
        "2. Indices and Primes": [
            "2.1 Factors, multiples, prime and composite numbers",
            "2.2 Prime factorisation and factor trees",
            "2.3 Index notation and evaluating powers",
            "2.4 Squares, square roots, cubes and cube roots",
            "2.5 Highest Common Factor and Lowest Common Multiple"
        ],
        "3. Fractions and Rational Numbers": [
            "3.1 Equivalent fractions and simplest form",
            "3.2 Mixed numbers and improper fractions",
            "3.3 Adding and subtracting fractions",
            "3.4 Multiplying fractions and finding fractions of quantities",
            "3.5 Dividing fractions and reciprocal operations"
        ],
        "4. Decimals and Place Value": [
            "4.1 Decimal place value and ordering decimals",
            "4.2 Rounding decimals and estimating results",
            "4.3 Adding and subtracting decimal numbers",
            "4.4 Multiplying and dividing decimals by whole numbers and powers of 10",
            "4.5 Converting between fractions and decimals"
        ],
        "5. Percentages and Proportions": [
            "5.1 Meaning of percentage and conversions (fraction-decimal-percentage)",
            "5.2 Calculating a percentage of a given amount",
            "5.3 Expressing one quantity as a percentage of another",
            "5.4 Percentage increases and decreases",
            "5.5 Practical financial discounts and markups"
        ],
        "6. Algebraic Expressions": [
            "6.1 Pronumerals, terms, coefficients and constant terms",
            "6.2 Writing algebraic expressions from verbal statements",
            "6.3 Substitution and evaluating formulas",
            "6.4 Adding and subtracting like terms",
            "6.5 Multiplying and dividing algebraic terms",
            "6.6 Expanding brackets using the distributive property"
        ],
        "7. Solving Equations": [
            "7.1 Concept of an equation and equivalent equations",
            "7.2 Solving one-step linear equations using inverse operations",
            "7.3 Solving two-step linear equations",
            "7.4 Equations with brackets and parentheses",
            "7.5 Formulating equations to solve word problems"
        ],
        "8. Angles and 2D Geometry": [
            "8.1 Measuring, classifying and drawing angles",
            "8.2 Complementary, supplementary and vertically opposite angles",
            "8.3 Angles associated with parallel lines: alternate, corresponding, co-interior",
            "8.4 Angle sum of triangles and exterior angle property",
            "8.5 Angle sum and properties of special quadrilaterals"
        ],
        "9. Length, Perimeter and Area": [
            "9.1 Units of length and perimeter of plane figures",
            "9.2 Circumference of circles and perimeter of composite shapes",
            "9.3 Area of rectangles, triangles and parallelograms",
            "9.4 Area of rhombuses, kites and trapeziums",
            "9.5 Area of circles and sectors"
        ],
        "10. Coordinate Geometry and Graphs": [
            "10.1 The Cartesian plane and plotting points",
            "10.2 Generating tables of values from linear algebraic rules",
            "10.3 Graphing linear relationships",
            "10.4 Interpreting real-life conversion and travel graphs"
        ],
        "11. Probability and Chance": [
            "11.1 The language of probability and chance experiments",
            "11.2 Theoretical probability of equally likely outcomes",
            "11.3 Complementary events",
            "11.4 Experimental probability and relative frequency",
            "11.5 Listing outcomes using lists, tables and tree diagrams"
        ],
        "12. Data Representation and Analysis": [
            "12.1 Collecting and classifying data: categorical vs numerical",
            "12.2 Frequency distribution tables and tally marks",
            "12.3 Dot plots, column graphs and histograms",
            "12.4 Stem-and-leaf plots",
            "12.5 Measures of central tendency: mean, median, mode",
            "12.6 Range and describing data distribution skewness"
        ]
    },
    "Year 8": {
        "1. Computation with Real Numbers": [
            "1.1 Integers and rational numbers",
            "1.2 Order of operations with directed numbers",
            "1.3 Decimals, rounding and significant figures",
            "1.4 Index laws for multiplication and division",
            "1.5 The zero index and power of a power"
        ],
        "2. Pythagoras' Theorem": [
            "2.1 The hypotenuse and right-angled triangle properties",
            "2.2 Pythagoras' theorem: c^2 = a^2 + b^2",
            "2.3 Calculating the hypotenuse length",
            "2.4 Calculating the length of a shorter side",
            "2.5 Applications of Pythagoras' theorem in 2D situations",
            "2.6 Pythagorean triads and testing for right angles"
        ],
        "3. Percentages, Ratios and Financial Mathematics": [
            "3.1 Ratio concepts and simplifying ratios",
            "3.2 Dividing quantities in a given ratio",
            "3.3 Unit rates and best-buy comparisons",
            "3.4 Percentage increase, decrease and reverse percentages",
            "3.5 Profit, loss, discount and retail pricing",
            "3.6 Simple interest formula: I = Prt"
        ],
        "4. Algebraic Techniques": [
            "4.1 Simplifying expressions by collecting like terms",
            "4.2 Index laws applied to algebraic variables",
            "4.3 Expanding single brackets using the distributive law",
            "4.4 Expanding and simplifying expressions with multiple brackets",
            "4.5 Factorising algebraic expressions by finding the HCF",
            "4.6 Operations on algebraic fractions with numerical denominators"
        ],
        "5. Linear Equations and Inequalities": [
            "5.1 Solving two-step linear equations",
            "5.2 Equations with pronumerals on both sides",
            "5.3 Equations containing grouping symbols and brackets",
            "5.4 Equations with simple algebraic fractions",
            "5.5 Writing equations to solve practical word problems",
            "5.6 Solving and graphing linear inequalities on a number line"
        ],
        "6. Geometric Reasoning and Congruence": [
            "6.1 Angle proofs on parallel lines and transversals",
            "6.2 Angle sum of polygons: interior and exterior angles",
            "6.3 Congruent triangle conditions: SSS, SAS, AAS, RHS",
            "6.4 Congruence proofs and applications",
            "6.5 Quadrilateral proofs using congruent triangles"
        ],
        "7. Length, Area, Surface Area and Volume": [
            "7.1 Perimeter and area of composite 2D shapes",
            "7.2 Surface area of rectangular and triangular prisms",
            "7.3 Volume of rectangular and triangular prisms (V = Ah)",
            "7.4 Surface area of cylinders: SA = 2*pi*r^2 + 2*pi*r*h",
            "7.5 Volume of cylinders: V = pi*r^2*h",
            "7.6 Capacity conversions and units of volume"
        ],
        "8. Linear Graphs and Relationships": [
            "8.1 Finding the gradient of a line: m = rise / run",
            "8.2 Finding the gradient using the formula m = (y2 - y1) / (x2 - x1)",
            "8.3 The gradient-intercept equation: y = mx + c",
            "8.4 Graphing linear equations using intercepts",
            "8.5 Horizontal and vertical lines: y = c, x = k",
            "8.6 Distance-time graphs and constant speed"
        ],
        "9. Probability and Two-Step Experiments": [
            "9.1 Sample spaces for two-step experiments",
            "9.2 Tree diagrams and probability tables",
            "9.3 Probability with and without replacement",
            "9.4 Venn diagrams and two-way tables",
            "9.5 Mutually exclusive events and the addition rule"
        ],
        "10. Investigating and Comparing Data": [
            "10.1 Grouped frequency distribution tables",
            "10.2 Grouped data histograms and polygons",
            "10.3 Mean, median, mode and range for grouped data",
            "10.4 Comparing two data sets using summary statistics",
            "10.5 Identifying and discussing the impact of outliers"
        ],
        "11. Similarity and Transformations": [
            "11.1 Similar shapes and scale factor calculation",
            "11.2 Tests for similar triangles (AAA, SAS, SSS, RHS)",
            "11.3 Finding missing side lengths in similar triangles",
            "11.4 Area and volume scale factors (k, k^2, k^3)"
        ]
    },
    "Year 9": {
        "1. Financial Mathematics": [
            "1.1 Wages, salaries, overtime and penalty rates",
            "1.2 Commission, piecework and royalties",
            "1.3 Taxable income, allowable deductions and tax brackets",
            "1.4 Simple interest loans and flat rate investments",
            "1.5 Compound interest formula: A = P(1 + r)^n",
            "1.6 Calculating future value and interest earned over time"
        ],
        "2. Indices and Surds": [
            "2.1 Review of index laws with integer exponents",
            "2.2 Negative indices: a^(-n) = 1 / a^n",
            "2.3 Fractional indices and radical form: a^(1/n) = sqrt[n](a)",
            "2.4 Simplifying surds and extracting square factors",
            "2.5 Adding and subtracting like surds",
            "2.6 Multiplying, dividing and expanding brackets with surds",
            "2.7 Rationalising the denominator"
        ],
        "3. Algebraic Techniques": [
            "3.1 Expanding binomial products: (a + b)(c + d)",
            "3.2 Special binomial expansions: perfect squares (a +/- b)^2 and difference of squares (a - b)(a + b)",
            "3.3 Factorising by taking out common factors",
            "3.4 Factorising by grouping in pairs",
            "3.5 Factorising monic quadratic trinomials: x^2 + bx + c",
            "3.6 Factorising non-monic quadratics: ax^2 + bx + c",
            "3.7 Operations on algebraic fractions"
        ],
        "4. Linear and Quadratic Equations": [
            "4.1 Solving complex linear equations with brackets and fractions",
            "4.2 Rearranging formulas and changing the subject",
            "4.3 Solving linear inequalities and number line representation",
            "4.4 Solving quadratic equations using the null factor law",
            "4.5 Solving quadratics by completing the square",
            "4.6 The quadratic formula: x = (-b +/- sqrt(b^2 - 4ac)) / (2a)",
            "4.7 Applications of quadratic equations in problem solving"
        ],
        "5. Coordinate Geometry and Linear Relationships": [
            "5.1 Distance between two points: d = sqrt((x2 - x1)^2 + (y2 - y1)^2)",
            "5.2 Midpoint of a segment: M = ((x1 + x2)/2, (y1 + y2)/2)",
            "5.3 Gradient of a straight line: m = (y2 - y1) / (x2 - x1)",
            "5.4 Gradient-intercept form: y = mx + c",
            "5.5 Point-gradient form: y - y1 = m(x - x1)",
            "5.6 General form: Ax + By + C = 0",
            "5.7 Parallel lines (m1 = m2) and perpendicular lines (m1 * m2 = -1)"
        ],
        "6. Right-Angled Trigonometry": [
            "6.1 Naming sides in a right triangle and trigonometric definitions",
            "6.2 Calculating unknown side lengths using sin, cos, tan",
            "6.3 Calculating unknown angles using inverse trig (sin^-1, cos^-1, tan^-1)",
            "6.4 Angles of elevation and depression",
            "6.5 Three-figure compass bearings and navigational problems",
            "6.6 Trigonometry in multi-step 2D problems"
        ],
        "7. Surface Area and Volume": [
            "7.1 Surface area of right prisms and cylinders",
            "7.2 Volume of right prisms and cylinders",
            "7.3 Surface area of right pyramids and cones",
            "7.4 Volume of pyramids and cones",
            "7.5 Surface area and volume of spheres and hemispheres"
        ],
        "8. Non-Linear Relationships": [
            "8.1 Graphing parabolas: y = ax^2 + c and features",
            "8.2 Graphing parabolas: y = a(x - h)^2 + k",
            "8.3 Graphing hyperbolas: y = k / x and asymptotes",
            "8.4 Graphing circles: x^2 + y^2 = r^2",
            "8.5 Graphing exponential functions: y = a^x"
        ],
        "9. Probability and Statistics": [
            "9.1 Multi-stage probability tree diagrams and arrays",
            "9.2 Independent vs dependent events and sampling without replacement",
            "9.3 Conditional probability in Venn diagrams and two-way tables",
            "9.4 Five-number summary, quartiles and interquartile range (IQR)",
            "9.5 Parallel box plots and identifying outliers",
            "9.6 Bivariate scatter plots, correlation and lines of best fit"
        ]
    },
    "Year 10": {
        "1. Financial Mathematics and Annuities": [
            "1.1 Compound interest calculations and formula: A = P(1 + r)^n",
            "1.2 Fractional compounding periods (monthly, quarterly, daily)",
            "1.3 Straight-line and declining-balance asset depreciation",
            "1.4 Credit card interest, repayments and personal loans",
            "1.5 Comparing superannuation growth and investment options"
        ],
        "2. Linear Systems and Coordinate Geometry": [
            "2.1 Linear equations review and equation of lines in various forms",
            "2.2 Parallel and perpendicular line relationships",
            "2.3 Solving simultaneous equations graphically",
            "2.4 Solving simultaneous equations algebraically: substitution and elimination",
            "2.5 Applications of simultaneous equations in business and physics",
            "2.6 Linear programming and half-plane inequalities intro"
        ],
        "3. Surface Area and Volume of Complex Figures": [
            "3.1 Surface area of composite 3D solids",
            "3.2 Volume of composite 3D solids",
            "3.3 Truncated pyramids and cones (frustums)",
            "3.4 Limits of accuracy, absolute error and percentage error"
        ],
        "4. Further Trigonometry": [
            "4.1 Trigonometry in 3D right-angled situations",
            "4.2 Navigational bearings and multi-triangle problems",
            "4.3 Angles of any magnitude and ASTC quadrant signs",
            "4.4 The Sine Rule for finding sides and angles",
            "4.5 The ambiguous case of the Sine Rule",
            "4.6 The Cosine Rule for finding sides and angles",
            "4.7 Area of any triangle: Area = 1/2 * a * b * sin(C)"
        ],
        "5. Quadratic Equations and Parabolic Functions (Advanced)": [
            "5.1 Factorising complex quadratic trinomials",
            "5.2 The quadratic formula and the discriminant Delta = b^2 - 4ac",
            "5.3 Nature of roots: real, equal, distinct, irrational, complex",
            "5.4 Turning point form: y = a(x - h)^2 + k and finding intercepts",
            "5.5 Maximum and minimum quadratic optimization word problems",
            "5.6 Intersections of straight lines and parabolas"
        ],
        "6. Functions, Graphs and Polynomials (Advanced)": [
            "6.1 Definition of a function, relations and the vertical line test",
            "6.2 Domain and range of functions in interval notation",
            "6.3 Graphing cubic functions: y = ax^3 and finding points of inflection",
            "6.4 Graphing circles, semi-circles and hyperbolas",
            "6.5 Polynomial long division and synthetic division",
            "6.6 The Remainder Theorem and Factor Theorem",
            "6.7 Solving cubic and quartic equations by factorisation"
        ],
        "7. Logarithms and Exponential Relations (Advanced)": [
            "7.1 Definition of a logarithm and conversion from index form",
            "7.2 Logarithmic laws: log(xy) = log(x) + log(y), log(x/y) = log(x) - log(y), log(x^p) = p*log(x)",
            "7.3 The zero and identity log rules: log_a(1) = 0, log_a(a) = 1",
            "7.4 Change of base formula: log_b(x) = log_a(x) / log_a(b)",
            "7.5 Solving exponential equations using logarithms",
            "7.6 Exponential growth and decay models"
        ],
        "8. Circle Geometry (Advanced)": [
            "8.1 Circle anatomy: chords, tangents, secants, cyclic polygons",
            "8.2 Chords of a circle: perpendicular bisector theorem and equal chords",
            "8.3 Angle at centre is twice angle at circumference",
            "8.4 Angles in the same segment and angle in a semicircle",
            "8.5 Cyclic quadrilaterals and supplementary opposite angles",
            "8.6 Tangents from an external point and radius-tangent perpendicularity",
            "8.7 The Alternate Segment Theorem"
        ],
        "9. Bivariate Data and Statistical Analysis": [
            "9.1 Bivariate scatter plots and interpreting associations",
            "9.2 Pearson's correlation coefficient r and strength of relationship",
            "9.3 The line of best fit and least-squares regression line intro",
            "9.4 Interpolation, extrapolation and evaluating reliability",
            "9.5 Correlation vs causation and lurking variables",
            "9.6 Standard deviation and interpreting normal distribution spreads"
        ],
        "10. Network Concepts and Graph Theory": [
            "10.1 Network terminology: vertices, edges, loops and degrees",
            "10.2 Planar graphs, faces and Euler's formula: v - e + f = 2",
            "10.3 Walks, trails, paths, circuits and cycles",
            "10.4 Eulerian and Hamiltonian paths and circuits",
            "10.5 Weighted networks and shortest path analysis (Dijkstra's method)",
            "10.6 Trees, minimum spanning trees and Kruskal's / Prim's algorithms",
            "10.7 Directed networks and adjacency matrices"
        ]
    }
}

MATHS_QUEST_CURRICULUM["Year 9 (Standard)"] = MATHS_QUEST_CURRICULUM["Year 9"]
MATHS_QUEST_CURRICULUM["Year 9 (Advanced)"] = MATHS_QUEST_CURRICULUM["Year 9"]
MATHS_QUEST_CURRICULUM["Year 10 (Standard)"] = MATHS_QUEST_CURRICULUM["Year 10"]
MATHS_QUEST_CURRICULUM["Year 10 (Advanced)"] = MATHS_QUEST_CURRICULUM["Year 10"]


# ==============================================================================
# 3. AUSTRALIAN SIGNPOST MATHEMATICS (PEARSON) - NSW 7-10 SYLLABUS
# ==============================================================================
SIGNPOST_CURRICULUM: Dict[str, Dict[str, List[str]]] = {
    "Year 7": {
        "1. Beginnings in Number": [
            "1.1 Place value and large numbers",
            "1.2 Mental computation and rounding strategies",
            "1.3 Order of operations with whole numbers",
            "1.4 Index notation and powers of 10",
            "1.5 Prime and composite numbers and divisibility rules"
        ],
        "2. Working Mathematically": [
            "2.1 Problem-solving strategies and heuristics",
            "2.2 Mathematical communication and notation",
            "2.3 Reasoning, justifying and conjecturing",
            "2.4 Investigating patterns in numbers and shapes"
        ],
        "3. Fractions and Rational Numbers": [
            "3.1 Equivalent fractions and simplifying",
            "3.2 Mixed numbers and improper fractions",
            "3.3 Adding and subtracting fractions",
            "3.4 Multiplying fractions and finding fractions of quantities",
            "3.5 Dividing fractions and reciprocal operations"
        ],
        "4. Patterns and Algebra": [
            "4.1 Describing number patterns and sequence rules",
            "4.2 Pronumerals, terms, coefficients and constants",
            "4.3 Writing algebraic expressions from worded descriptions",
            "4.4 Substitution into algebraic expressions",
            "4.5 Collecting like terms by addition and subtraction",
            "4.6 Multiplying and dividing algebraic terms"
        ],
        "5. Angles and Geometrical Figures": [
            "5.1 Measuring, naming and classifying angles",
            "5.2 Complementary and supplementary angles",
            "5.3 Angles at a point and vertically opposite angles",
            "5.4 Parallel lines and angles: alternate, corresponding, co-interior",
            "5.5 Triangle classifications and angle sum of a triangle"
        ],
        "6. Decimals": [
            "6.1 Decimal place value and ordering on the number line",
            "6.2 Rounding decimals and estimating calculations",
            "6.3 Adding and subtracting decimal numbers",
            "6.4 Multiplying and dividing decimals by whole numbers and powers of 10",
            "6.5 Converting fractions to decimals and decimals to fractions"
        ],
        "7. Directed Numbers and the Number Plane": [
            "7.1 Negative numbers in real contexts",
            "7.2 Adding and subtracting directed numbers",
            "7.3 Multiplying and dividing directed numbers",
            "7.4 Order of operations with integers",
            "7.5 Plotting points and reading coordinates on the Cartesian plane"
        ],
        "8. 2D and 3D Space": [
            "8.1 Properties of quadrilaterals: squares, rectangles, rhombuses, trapezia, kites",
            "8.2 Congruent figures and symmetry (line and rotational)",
            "8.3 Transformations: translations, reflections and rotations",
            "8.4 Solids, nets, vertices, edges and faces of 3D prisms and pyramids"
        ],
        "9. Perimeter, Area and Volume": [
            "9.1 Units of length and perimeter of plane figures",
            "9.2 Circumference of circles and perimeter of sectors",
            "9.3 Area of squares, rectangles, triangles and parallelograms",
            "9.4 Area of rhombuses, kites and trapeziums",
            "9.5 Area of circles and composite figures",
            "9.6 Volume and capacity of rectangular prisms"
        ],
        "10. Percentages": [
            "10.1 Understanding percentages and conversions (fractions, decimals, percentages)",
            "10.2 Calculating a percentage of a quantity",
            "10.3 Expressing one quantity as a percentage of another",
            "10.4 Percentage increase and decrease",
            "10.5 Practical commercial discounts and profits"
        ],
        "11. Equations": [
            "11.1 Concept of an equation and algebraic balance",
            "11.2 Solving one-step linear equations using inverse operations",
            "11.3 Solving two-step linear equations",
            "11.4 Equations involving grouping symbols and brackets",
            "11.5 Solving practical problems using linear equations"
        ],
        "12. Probability": [
            "12.1 The probability scale from impossible (0) to certain (1)",
            "12.2 Calculating theoretical probability of simple events",
            "12.3 Complementary events: P(not A) = 1 - P(A)",
            "12.4 Experimental probability and relative frequency",
            "12.5 Sample spaces and two-way tables"
        ],
        "13. Statistics and Data": [
            "13.1 Types of data: categorical and numerical",
            "13.2 Frequency tables and tally marks",
            "13.3 Displaying data: column graphs, dot plots and histograms",
            "13.4 Stem-and-leaf plots",
            "13.5 Measures of central tendency: mean, median, mode",
            "13.6 Measure of spread: range and detecting outliers"
        ]
    },
    "Year 8": {
        "1. Working Mathematically and Year 7 Review": [
            "1.1 Directed numbers and integer arithmetic review",
            "1.2 Order of operations and grouping symbols",
            "1.3 Fractions, decimals and percentage conversions",
            "1.4 Index laws and powers of 10"
        ],
        "2. Pythagoras' Theorem": [
            "2.1 Right-angled triangles and identifying the hypotenuse",
            "2.2 Pythagoras' rule: c^2 = a^2 + b^2",
            "2.3 Calculating the length of the hypotenuse",
            "2.4 Calculating the length of a shorter side",
            "2.5 Pythagorean triads and verifying right angles",
            "2.6 Real-world practical 2D problems"
        ],
        "3. Percentages, Ratios and Financial Mathematics": [
            "3.1 Ratio concepts and simplifying ratios",
            "3.2 Dividing quantities in a given ratio",
            "3.3 Unit rates, best buys and comparison shopping",
            "3.4 Finding the original quantity after percentage change",
            "3.5 Profit and loss calculations",
            "3.6 Simple interest formula: I = Prt"
        ],
        "4. Algebraic Techniques": [
            "4.1 Collecting like terms and index laws in algebra",
            "4.2 Expanding single brackets using the distributive law",
            "4.3 Expanding and simplifying expressions with multiple brackets",
            "4.4 Factorising expressions by taking out the HCF",
            "4.5 Simplifying algebraic fractions with numerical denominators"
        ],
        "5. Equations and Inequalities": [
            "5.1 Solving two-step linear equations",
            "5.2 Equations with pronumerals on both sides",
            "5.3 Equations with brackets and parentheses",
            "5.4 Equations with simple algebraic fractions",
            "5.5 Writing equations to solve practical word problems",
            "5.6 Solving and graphing linear inequalities on a number line"
        ],
        "6. Geometric Reasoning and Congruence": [
            "6.1 Angle proofs on parallel lines and transversals",
            "6.2 Angle sum and exterior angle theorem of triangles",
            "6.3 Interior and exterior angles of polygons",
            "6.4 Congruent triangle tests: SSS, SAS, AAS, RHS",
            "6.5 Formal geometric congruence proofs"
        ],
        "7. Perimeter, Area, Surface Area and Volume": [
            "7.1 Perimeter and area of composite 2D shapes",
            "7.2 Surface area of rectangular and triangular prisms",
            "7.3 Volume of right prisms: V = Ah",
            "7.4 Surface area of cylinders: SA = 2*pi*r^2 + 2*pi*r*h",
            "7.5 Volume of cylinders: V = pi*r^2*h",
            "7.6 Units of volume, capacity and conversions"
        ],
        "8. Linear Relationships and Graphs": [
            "8.1 Finding the gradient of a straight line: rise over run",
            "8.2 Finding the gradient using formula m = (y2 - y1) / (x2 - x1)",
            "8.3 The gradient-intercept form: y = mx + c",
            "8.4 Graphing straight lines using intercepts",
            "8.5 Horizontal and vertical lines: y = c, x = k",
            "8.6 Distance-time graphs and travel rate interpretation"
        ],
        "9. Probability and Two-Step Experiments": [
            "9.1 Sample spaces for two-step experiments",
            "9.2 Tree diagrams and probability tables",
            "9.3 Probability with and without replacement",
            "9.4 Venn diagrams and two-way tables",
            "9.5 Mutually exclusive events and the addition rule"
        ],
        "10. Investigating and Comparing Data": [
            "10.1 Grouped frequency distribution tables",
            "10.2 Grouped data histograms and frequency polygons",
            "10.3 Mean, median, mode and range for grouped data",
            "10.4 Comparing two data sets using summary statistics",
            "10.5 Identifying outliers and analyzing their effect"
        ]
    },
    "Year 9": {
        "1. Financial Management": [
            "1.1 Wages, salaries, overtime and penalty rates",
            "1.2 Commission, piecework and royalties",
            "1.3 Income tax, allowable deductions and Medicare levy",
            "1.4 Simple interest loans and flat rate investments",
            "1.5 Compound interest formula: A = P(1 + r)^n",
            "1.6 Calculating future value and total interest"
        ],
        "2. Algebra, Indices and Surds": [
            "2.1 Index laws review and negative indices: a^(-n) = 1 / a^n",
            "2.2 Fractional indices: a^(1/n) = sqrt[n](a)",
            "2.3 Simplifying surds and extracting square factors",
            "2.4 Adding, subtracting, multiplying and dividing surds",
            "2.5 Expanding brackets with surds and rationalising denominators",
            "2.6 Expanding binomial products: (a + b)(c + d)",
            "2.7 Special products: (a +/- b)^2 and difference of squares",
            "2.8 Factorising quadratic trinomials: monic and non-monic"
        ],
        "3. Linear Equations and Inequalities": [
            "3.1 Solving multi-step linear equations with brackets and fractions",
            "3.2 Rearranging and transposing formulas",
            "3.3 Solving linear inequalities and number line representation",
            "3.4 Solving quadratic equations using the null factor law",
            "3.5 Solving quadratics by completing the square and quadratic formula"
        ],
        "4. Coordinate Geometry and Linear Relationships": [
            "4.1 Distance between two points: d = sqrt((x2 - x1)^2 + (y2 - y1)^2)",
            "4.2 Midpoint of a segment: M = ((x1 + x2)/2, (y1 + y2)/2)",
            "4.3 Gradient of a line: m = (y2 - y1) / (x2 - x1)",
            "4.4 Gradient-intercept form: y = mx + b and general form Ax + By + C = 0",
            "4.5 Point-gradient form: y - y1 = m(x - x1)",
            "4.6 Parallel lines (m1 = m2) and perpendicular lines (m1 * m2 = -1)"
        ],
        "5. Measurement and Surface Area": [
            "5.1 Area of composite 2D shapes and circles",
            "5.2 Surface area of right prisms and cylinders",
            "5.3 Volume of right prisms and cylinders",
            "5.4 Surface area of pyramids and cones",
            "5.5 Volume of pyramids, cones and spheres"
        ],
        "6. Trigonometry": [
            "6.1 Naming sides in a right triangle and trigonometric definitions",
            "6.2 Calculating unknown side lengths using sin, cos, tan",
            "6.3 Calculating unknown angles using inverse trig",
            "6.4 Angles of elevation and depression",
            "6.5 Three-figure compass bearings and navigational problems",
            "6.6 Trigonometry in 2D practical problems"
        ],
        "7. Geometry and Deductive Proofs": [
            "7.1 Angle theorems and parallel line proofs",
            "7.2 Congruent triangle proofs and applications",
            "7.3 Similar triangle proofs and finding unknown sides",
            "7.4 Quadrilateral proofs using deductive reasoning"
        ],
        "8. Statistics and Probability": [
            "8.1 Multi-stage probability tree diagrams with and without replacement",
            "8.2 Conditional probability in two-way tables and Venn diagrams",
            "8.3 Five-number summary, quartiles and interquartile range (IQR)",
            "8.4 Constructing and interpreting box plots and detecting outliers",
            "8.5 Bivariate scatter plots, correlation and trend lines"
        ],
        "9. Non-Linear Relationships": [
            "9.1 Graphing parabolas: y = ax^2 + c and features",
            "9.2 Graphing parabolas: y = a(x - h)^2 + k",
            "9.3 Graphing hyperbolas: y = k / x and asymptotes",
            "9.4 Graphing circles: x^2 + y^2 = r^2",
            "9.5 Graphing exponential functions: y = a^x"
        ]
    },
    "Year 10": {
        "1. Quadratic Equations and Parabolic Functions": [
            "1.1 Factorising non-monic quadratics: ax^2 + bx + c",
            "1.2 Solving quadratics by completing the square and quadratic formula",
            "1.3 The discriminant Delta = b^2 - 4ac and nature of roots",
            "1.4 Parabola vertex form: y = a(x - h)^2 + k and finding intercepts",
            "1.5 Maximum and minimum quadratic optimization word problems",
            "1.6 Simultaneous equations involving one linear and one quadratic equation"
        ],
        "2. Financial Mathematics and Depreciation": [
            "2.1 Compound interest calculations and formula: A = P(1 + r)^n",
            "2.2 Fractional compounding periods (monthly, quarterly, daily)",
            "2.3 Straight-line and declining-balance asset depreciation",
            "2.4 Credit card interest, repayments and personal loans",
            "2.5 Comparing superannuation growth and investment options"
        ],
        "3. Linear and Non-Linear Relationships": [
            "3.1 Linear equations review and equation of lines in various forms",
            "3.2 Parallel and perpendicular line relationships",
            "3.3 Solving simultaneous equations graphically",
            "3.4 Solving simultaneous equations algebraically: substitution and elimination",
            "3.5 Applications of simultaneous equations in business and physics",
            "3.6 Graphing hyperbolas, circles and exponential curves"
        ],
        "4. Surface Area and Volume": [
            "4.1 Surface area of composite 3D solids",
            "4.2 Volume of composite 3D solids",
            "4.3 Truncated pyramids and cones (frustums)",
            "4.4 Limits of accuracy, absolute error and percentage error"
        ],
        "5. Further Trigonometry": [
            "5.1 Trigonometry in 3D right-angled situations",
            "5.2 Navigational bearings and multi-triangle problems",
            "5.3 Angles of any magnitude and ASTC quadrant signs",
            "5.4 The Sine Rule for finding sides and angles",
            "5.5 The ambiguous case of the Sine Rule",
            "5.6 The Cosine Rule for finding sides and angles",
            "5.7 Area of any triangle: Area = 1/2 * a * b * sin(C)"
        ],
        "6. Circle Geometry (Advanced)": [
            "6.1 Circle anatomy: chords, tangents, secants, cyclic polygons",
            "6.2 Chords of a circle: perpendicular bisector theorem and equal chords",
            "6.3 Angle at centre is twice angle at circumference",
            "6.4 Angles in the same segment and angle in a semicircle",
            "6.5 Cyclic quadrilaterals and supplementary opposite angles",
            "6.6 Tangents from an external point and radius-tangent perpendicularity",
            "6.7 The Alternate Segment Theorem"
        ],
        "7. Polynomials and Functions (Advanced)": [
            "7.1 Definition of a function, relations and the vertical line test",
            "7.2 Domain and range of functions in interval notation",
            "7.3 Graphing cubic functions: y = ax^3 and finding points of inflection",
            "7.4 Graphing circles, semi-circles and hyperbolas",
            "7.5 Polynomial long division and synthetic division",
            "7.6 The Remainder Theorem and Factor Theorem",
            "7.7 Solving cubic and quartic equations by factorisation"
        ],
        "8. Logarithms and Exponential Relations (Advanced)": [
            "8.1 Definition of a logarithm and conversion from index form",
            "8.2 Logarithmic laws: log(xy) = log(x) + log(y), log(x/y) = log(x) - log(y), log(x^p) = p*log(x)",
            "8.3 The zero and identity log rules: log_a(1) = 0, log_a(a) = 1",
            "8.4 Change of base formula: log_b(x) = log_a(x) / log_a(b)",
            "8.5 Solving exponential equations using logarithms",
            "8.6 Exponential growth and decay models"
        ],
        "9. Bivariate Data and Statistics": [
            "9.1 Bivariate scatter plots and interpreting associations",
            "9.2 Pearson's correlation coefficient r and strength of relationship",
            "9.3 The line of best fit and least-squares regression line intro",
            "9.4 Interpolation, extrapolation and evaluating reliability",
            "9.5 Correlation vs causation and lurking variables",
            "9.6 Standard deviation and interpreting normal distribution spreads"
        ],
        "10. Network Concepts and Optimisation": [
            "10.1 Introduction to networks: vertices, edges, degree and multiple edges",
            "10.2 Connected and planar graphs: Euler's formula (v - e + f = 2)",
            "10.3 Traversable networks: Eulerian and Hamiltonian paths and circuits",
            "10.4 Weighted networks and shortest path problems",
            "10.5 Minimum spanning trees and network optimisation (Prim's algorithm)",
            "10.6 Directed networks and adjacency matrices"
        ]
    }
}

SIGNPOST_CURRICULUM["Year 9 (Standard)"] = SIGNPOST_CURRICULUM["Year 9"]
SIGNPOST_CURRICULUM["Year 9 (Advanced)"] = SIGNPOST_CURRICULUM["Year 9"]
SIGNPOST_CURRICULUM["Year 10 (Standard)"] = SIGNPOST_CURRICULUM["Year 10"]
SIGNPOST_CURRICULUM["Year 10 (Advanced)"] = SIGNPOST_CURRICULUM["Year 10"]


# ==============================================================================
# 4. OXFORD MATHS NSW (OXFORD UNIVERSITY PRESS) - NSW 7-10 SYLLABUS
# ==============================================================================
OXFORD_CURRICULUM: Dict[str, Dict[str, List[str]]] = {
    "Year 7": {
        "1. Number and Calculations": [
            "1.1 Place value, whole numbers and mental strategies",
            "1.2 Adding, subtracting, multiplying and dividing whole numbers",
            "1.3 Order of operations and grouping symbols (BODMAS)",
            "1.4 Directed numbers and integers on the number line",
            "1.5 Operations with negative integers"
        ],
        "2. Indices and Primes": [
            "2.1 Prime and composite numbers and factor trees",
            "2.2 Divisibility tests and index notation",
            "2.3 Squares, square roots, cubes and cube roots",
            "2.4 Highest Common Factor and Lowest Common Multiple"
        ],
        "3. Fractions and Decimals": [
            "3.1 Equivalent fractions and simplifying",
            "3.2 Adding and subtracting fractions",
            "3.3 Multiplying and dividing fractions",
            "3.4 Decimal place value and decimal arithmetic",
            "3.5 Converting between fractions and decimals"
        ],
        "4. Percentages": [
            "4.1 Understanding percentages and conversions",
            "4.2 Calculating a percentage of a quantity",
            "4.3 Expressing one quantity as a percentage of another",
            "4.4 Percentage increase and decrease",
            "4.5 Discounts and financial applications"
        ],
        "5. Algebra and Variables": [
            "5.1 Using letters to represent numbers and write expressions",
            "5.2 Evaluating expressions by substitution",
            "5.3 Collecting like terms (addition and subtraction)",
            "5.4 Multiplying and dividing algebraic terms",
            "5.5 Expanding single brackets using the distributive property",
            "5.6 Solving one-step and two-step linear equations"
        ],
        "6. Angles and Parallel Lines": [
            "6.1 Classifying and measuring angles with a protractor",
            "6.2 Complementary, supplementary and vertically opposite angles",
            "6.3 Angles formed by parallel lines and transversals",
            "6.4 Angle sum of triangles and quadrilaterals"
        ],
        "7. 2D and 3D Shapes": [
            "7.1 Classifying triangles and quadrilaterals",
            "7.2 Congruence of shapes and identifying corresponding sides",
            "7.3 Symmetry: line symmetry and rotational symmetry",
            "7.4 Drawing and building 3D solids: isometric drawings and nets"
        ],
        "8. Perimeter, Area and Volume": [
            "8.1 Perimeter of polygons and circumference of circles",
            "8.2 Area of rectangles, triangles, parallelograms and rhombuses",
            "8.3 Area of trapeziums and circles",
            "8.4 Area of composite 2D shapes",
            "8.5 Volume and capacity of rectangular prisms"
        ],
        "9. The Number Plane": [
            "9.1 The Cartesian coordinate system and quadrants",
            "9.2 Plotting and reading points (x, y)",
            "9.3 Generating a table of values from a linear rule",
            "9.4 Graphing straight lines on the number plane",
            "9.5 Interpreting travel graphs and conversion graphs"
        ],
        "10. Probability and Statistics": [
            "10.1 Probability scale and chance language",
            "10.2 Calculating theoretical probability of simple events",
            "10.3 Complementary events",
            "10.4 Collecting and tabulating data in frequency tables",
            "10.5 Column graphs, histograms and dot plots",
            "10.6 Summary statistics: mean, median, mode and range"
        ]
    },
    "Year 8": {
        "1. Integers and Real Numbers": [
            "1.1 Real number system: rational and irrational numbers",
            "1.2 Combined operations with directed numbers",
            "1.3 Index laws for multiplying and dividing powers",
            "1.4 The zero index and power of a power",
            "1.5 Expressing large numbers in scientific notation"
        ],
        "2. Pythagoras' Theorem": [
            "2.1 Identifying the hypotenuse in right-angled triangles",
            "2.2 Pythagoras' theorem: c^2 = a^2 + b^2",
            "2.3 Calculating the length of the hypotenuse",
            "2.4 Calculating the length of a shorter side",
            "2.5 Pythagorean triads and verifying right angles",
            "2.6 Practical 2D applications of Pythagoras' theorem"
        ],
        "3. Ratios, Rates and Percentages": [
            "3.1 Ratio concepts and simplifying ratios",
            "3.2 Dividing a quantity in a given ratio",
            "3.3 Unit rates, constant speed and unit pricing",
            "3.4 Percentage increase and decrease and finding original quantity",
            "3.5 Profit, loss and percentage profit/loss",
            "3.6 Simple interest formula: I = Prt"
        ],
        "4. Algebraic Techniques": [
            "4.1 Simplifying expressions by collecting like terms",
            "4.2 Index laws applied to algebraic terms",
            "4.3 Expanding single brackets using the distributive property",
            "4.4 Expanding and simplifying expressions with multiple brackets",
            "4.5 Factorising algebraic expressions by finding the HCF",
            "4.6 Simplifying algebraic fractions with numerical denominators"
        ],
        "5. Linear Equations and Inequalities": [
            "5.1 Solving multi-step linear equations",
            "5.2 Equations with pronumerals on both sides",
            "5.3 Equations with brackets and parentheses",
            "5.4 Equations with simple algebraic fractions",
            "5.5 Formulating equations to solve practical word problems",
            "5.6 Solving and graphing linear inequalities on a number line"
        ],
        "6. Geometric Properties and Angles": [
            "6.1 Angle proofs on parallel lines and transversals",
            "6.2 Angle sum and exterior angle theorem of triangles",
            "6.3 Interior and exterior angles of polygons",
            "6.4 Congruent triangle tests: SSS, SAS, AAS, RHS",
            "6.5 Formal geometric congruence proofs"
        ],
        "7. Length, Area, Surface Area and Volume": [
            "7.1 Perimeter and area of composite 2D shapes",
            "7.2 Surface area of rectangular and triangular prisms",
            "7.3 Volume of right prisms (V = Ah)",
            "7.4 Surface area of cylinders: SA = 2*pi*r^2 + 2*pi*r*h",
            "7.5 Volume of cylinders: V = pi*r^2*h",
            "7.6 Units of volume, capacity and conversions"
        ],
        "8. Linear Relationships and Graphs": [
            "8.1 Finding the gradient of a straight line: rise over run",
            "8.2 Finding the gradient using formula m = (y2 - y1) / (x2 - x1)",
            "8.3 The gradient-intercept form: y = mx + c",
            "8.4 Graphing straight lines using intercepts",
            "8.5 Horizontal and vertical lines: y = c, x = k",
            "8.6 Distance-time graphs and travel rate interpretation"
        ],
        "9. Probability and Multi-Step Experiments": [
            "9.1 Sample spaces for two-step experiments",
            "9.2 Tree diagrams and probability tables",
            "9.3 Probability with and without replacement",
            "9.4 Venn diagrams and two-way tables",
            "9.5 Mutually exclusive events and the addition rule"
        ],
        "10. Investigating and Comparing Data": [
            "10.1 Grouped frequency distribution tables",
            "10.2 Grouped data histograms and frequency polygons",
            "10.3 Mean, median, mode and range for grouped data",
            "10.4 Comparing two data sets using summary statistics",
            "10.5 Identifying outliers and analyzing their effect"
        ]
    },
    "Year 9": {
        "1. Financial Mathematics": [
            "1.1 Wages, salaries, overtime and penalty rates",
            "1.2 Commission, piecework and royalties",
            "1.3 Taxable income, allowable deductions and tax brackets",
            "1.4 Simple interest loans and flat rate investments",
            "1.5 Compound interest formula: A = P(1 + r)^n",
            "1.6 Calculating future value and interest earned over time"
        ],
        "2. Indices and Surds": [
            "2.1 Review of index laws with integer exponents",
            "2.2 Negative indices: a^(-n) = 1 / a^n",
            "2.3 Fractional indices and radical form: a^(1/n) = sqrt[n](a)",
            "2.4 Simplifying surds and extracting square factors",
            "2.5 Adding and subtracting like surds",
            "2.6 Multiplying, dividing and expanding brackets with surds",
            "2.7 Rationalising the denominator"
        ],
        "3. Algebraic Techniques and Binomial Expansion": [
            "3.1 Expanding binomial products: (a + b)(c + d)",
            "3.2 Special binomial expansions: perfect squares and difference of squares",
            "3.3 Factorising by taking out common factors",
            "3.4 Factorising by grouping in pairs",
            "3.5 Factorising monic quadratic trinomials: x^2 + bx + c",
            "3.6 Factorising non-monic quadratics: ax^2 + bx + c",
            "3.7 Operations on algebraic fractions"
        ],
        "4. Linear and Quadratic Equations": [
            "4.1 Solving complex linear equations with brackets and fractions",
            "4.2 Rearranging formulas and changing the subject",
            "4.3 Solving linear inequalities and number line representation",
            "4.4 Solving quadratic equations using the null factor law",
            "4.5 Solving quadratics by completing the square",
            "4.6 The quadratic formula: x = (-b +/- sqrt(b^2 - 4ac)) / (2a)",
            "4.7 Applications of quadratic equations in problem solving"
        ],
        "5. Coordinate Geometry and Linear Relationships": [
            "5.1 Distance between two points: d = sqrt((x2 - x1)^2 + (y2 - y1)^2)",
            "5.2 Midpoint of a segment: M = ((x1 + x2)/2, (y1 + y2)/2)",
            "5.3 Gradient of a straight line: m = (y2 - y1) / (x2 - x1)",
            "5.4 Gradient-intercept form: y = mx + c",
            "5.5 Point-gradient form: y - y1 = m(x - x1)",
            "5.6 General form: Ax + By + C = 0",
            "5.7 Parallel lines (m1 = m2) and perpendicular lines (m1 * m2 = -1)"
        ],
        "6. Right-Angled Trigonometry": [
            "6.1 Naming sides in a right triangle and trigonometric definitions",
            "6.2 Calculating unknown side lengths using sin, cos, tan",
            "6.3 Calculating unknown angles using inverse trig",
            "6.4 Angles of elevation and depression",
            "6.5 Three-figure compass bearings and navigational problems",
            "6.6 Trigonometry in multi-step 2D problems"
        ],
        "7. Surface Area and Volume": [
            "7.1 Surface area of right prisms and cylinders",
            "7.2 Volume of right prisms and cylinders",
            "7.3 Surface area of right pyramids and cones",
            "7.4 Volume of pyramids and cones",
            "7.5 Surface area and volume of spheres and hemispheres"
        ],
        "8. Non-Linear Relationships": [
            "8.1 Graphing parabolas: y = ax^2 + c and features",
            "8.2 Graphing parabolas: y = a(x - h)^2 + k",
            "8.3 Graphing hyperbolas: y = k / x and asymptotes",
            "8.4 Graphing circles: x^2 + y^2 = r^2",
            "8.5 Graphing exponential functions: y = a^x"
        ],
        "9. Probability and Statistics": [
            "9.1 Multi-stage probability tree diagrams and arrays",
            "9.2 Independent vs dependent events and sampling without replacement",
            "9.3 Conditional probability in Venn diagrams and two-way tables",
            "9.4 Five-number summary, quartiles and interquartile range (IQR)",
            "9.5 Parallel box plots and identifying outliers",
            "9.6 Bivariate scatter plots, correlation and lines of best fit"
        ]
    },
    "Year 10": {
        "1. Advanced Algebra and Polynomials": [
            "1.1 Factorising non-monic quadratics: ax^2 + bx + c",
            "1.2 Solving quadratics by completing the square and quadratic formula",
            "1.3 The discriminant Delta = b^2 - 4ac and nature of roots",
            "1.4 Polynomial definitions, degree and leading coefficient",
            "1.5 Polynomial long division and synthetic division",
            "1.6 The Remainder Theorem and Factor Theorem",
            "1.7 Solving cubic equations by factorisation"
        ],
        "2. Functions and Non-Linear Graphs": [
            "2.1 Function definition, function notation and vertical line test",
            "2.2 Domain and range of functions in interval notation",
            "2.3 Graphing parabolas: y = a(x - h)^2 + k and finding intercepts",
            "2.4 Graphing cubic functions and transformations",
            "2.5 Graphing hyperbolas, circles and exponential curves",
            "2.6 Maximum and minimum quadratic optimization word problems"
        ],
        "3. Financial Mathematics and Depreciation": [
            "3.1 Compound interest calculations and formula: A = P(1 + r)^n",
            "3.2 Fractional compounding periods (monthly, quarterly, daily)",
            "3.3 Straight-line and declining-balance asset depreciation",
            "3.4 Credit card interest, repayments and personal loans",
            "3.5 Comparing superannuation growth and investment options"
        ],
        "4. Linear Systems and Coordinate Geometry": [
            "4.1 Linear equations review and equation of lines in various forms",
            "4.2 Parallel and perpendicular line relationships",
            "4.3 Solving simultaneous equations graphically",
            "4.4 Solving simultaneous equations algebraically: substitution and elimination",
            "4.5 Applications of simultaneous equations in business and physics"
        ],
        "5. Further Trigonometry": [
            "5.1 Trigonometry in 3D right-angled situations",
            "5.2 Navigational bearings and multi-triangle problems",
            "5.3 Angles of any magnitude and ASTC quadrant signs",
            "5.4 The Sine Rule for finding sides and angles",
            "5.5 The ambiguous case of the Sine Rule",
            "5.6 The Cosine Rule for finding sides and angles",
            "5.7 Area of any triangle: Area = 1/2 * a * b * sin(C)"
        ],
        "6. Surface Area and Volume of Complex Solids": [
            "6.1 Surface area of composite 3D solids",
            "6.2 Volume of composite 3D solids",
            "6.3 Truncated pyramids and cones (frustums)",
            "6.4 Limits of accuracy, absolute error and percentage error"
        ],
        "7. Circle Geometry (Advanced)": [
            "7.1 Circle anatomy: chords, tangents, secants, cyclic polygons",
            "7.2 Chords of a circle: perpendicular bisector theorem and equal chords",
            "7.3 Angle at centre is twice angle at circumference",
            "7.4 Angles in the same segment and angle in a semicircle",
            "7.5 Cyclic quadrilaterals and supplementary opposite angles",
            "7.6 Tangents from an external point and radius-tangent perpendicularity",
            "7.7 The Alternate Segment Theorem"
        ],
        "8. Logarithms and Exponential Relations (Advanced)": [
            "8.1 Definition of a logarithm and conversion from index form",
            "8.2 Logarithmic laws: log(xy) = log(x) + log(y), log(x/y) = log(x) - log(y), log(x^p) = p*log(x)",
            "8.3 The zero and identity log rules: log_a(1) = 0, log_a(a) = 1",
            "8.4 Change of base formula: log_b(x) = log_a(x) / log_a(b)",
            "8.5 Solving exponential equations using logarithms",
            "8.6 Exponential growth and decay models"
        ],
        "9. Bivariate Data and Statistics": [
            "9.1 Bivariate scatter plots and interpreting associations",
            "9.2 Pearson's correlation coefficient r and strength of relationship",
            "9.3 The line of best fit and least-squares regression line intro",
            "9.4 Interpolation, extrapolation and evaluating reliability",
            "9.5 Correlation vs causation and lurking variables",
            "9.6 Standard deviation and interpreting normal distribution spreads"
        ],
        "10. Network Concepts": [
            "10.1 Network definitions: vertices, edges, loops, degrees and directed graphs",
            "10.2 Planar graphs, regions and Euler's formula: v - e + f = 2",
            "10.3 Paths, cycles, Eulerian and Hamiltonian traversals",
            "10.4 Shortest paths and weighted network analysis",
            "10.5 Trees, minimum spanning trees and Kruskal's/Prim's algorithms",
            "10.6 Adjacency matrices and network connectivity"
        ]
    }
}

OXFORD_CURRICULUM["Year 9 (Standard)"] = OXFORD_CURRICULUM["Year 9"]
OXFORD_CURRICULUM["Year 9 (Advanced)"] = OXFORD_CURRICULUM["Year 9"]
OXFORD_CURRICULUM["Year 10 (Standard)"] = OXFORD_CURRICULUM["Year 10"]
OXFORD_CURRICULUM["Year 10 (Advanced)"] = OXFORD_CURRICULUM["Year 10"]


# ==============================================================================
# 5. MATHSCAPE (MACMILLAN EDUCATION) - NSW 7-10 SYLLABUS
# ==============================================================================
MATHSCAPE_CURRICULUM: Dict[str, Dict[str, List[str]]] = {
    "Year 7": {
        "1. Whole Numbers and Operations": [
            "1.1 Place value and large whole numbers",
            "1.2 Mental computation strategies and estimation",
            "1.3 Adding, subtracting, multiplying and dividing whole numbers",
            "1.4 Order of operations with brackets (BODMAS)",
            "1.5 Prime, composite numbers and factor trees",
            "1.6 Highest Common Factor and Lowest Common Multiple"
        ],
        "2. Integers and the Number Plane": [
            "2.1 Directed numbers in everyday life",
            "2.2 Adding and subtracting integers",
            "2.3 Multiplying and dividing directed numbers",
            "2.4 Combined operations with integers",
            "2.5 The Cartesian number plane and plotting coordinates"
        ],
        "3. Fractions, Decimals and Percentages": [
            "3.1 Equivalent fractions and simplifying",
            "3.2 Mixed numbers and improper fractions",
            "3.3 Operations on fractions: addition, subtraction, multiplication, division",
            "3.4 Decimal place value and decimal arithmetic",
            "3.5 Conversions between fractions, decimals and percentages",
            "3.6 Percentage of a quantity and simple financial discounts"
        ],
        "4. Introduction to Algebra": [
            "4.1 Using letters for unknown numbers and pronumerals",
            "4.2 Writing algebraic expressions from verbal statements",
            "4.3 Substitution and evaluating formulas",
            "4.4 Collecting like terms by addition and subtraction",
            "4.5 Multiplying and dividing algebraic terms",
            "4.6 Expanding single brackets using the distributive property",
            "4.7 Solving one-step and two-step linear equations"
        ],
        "5. Angles and Geometric Figures": [
            "5.1 Naming, classifying and measuring angles",
            "5.2 Complementary, supplementary and vertically opposite angles",
            "5.3 Angles on parallel lines: alternate, corresponding, co-interior",
            "5.4 Angle sum of triangles and quadrilaterals",
            "5.5 Classifying triangles, quadrilaterals and regular polygons"
        ],
        "6. Perimeter and Area": [
            "6.1 Metric units of length and perimeter of plane figures",
            "6.2 Circumference of circles and perimeter of sectors",
            "6.3 Area of rectangles, triangles and parallelograms",
            "6.4 Area of rhombuses, kites and trapeziums",
            "6.5 Area of circles and composite figures",
            "6.6 Volume and capacity of rectangular prisms"
        ],
        "7. Probability and Statistics": [
            "7.1 Probability scale and language of chance",
            "7.2 Calculating theoretical probability of simple events",
            "7.3 Complementary events: P(not A) = 1 - P(A)",
            "7.4 Frequency distribution tables and tally charts",
            "7.5 Column graphs, dot plots and histograms",
            "7.6 Summary statistics: mean, median, mode and range"
        ]
    },
    "Year 8": {
        "1. Number Skills and Indices": [
            "1.1 Directed numbers and order of operations review",
            "1.2 Real numbers: rational and irrational numbers",
            "1.3 Index laws for multiplication and division",
            "1.4 The zero index and power of a power",
            "1.5 Expressing large numbers in scientific notation"
        ],
        "2. Pythagoras' Theorem": [
            "2.1 Identifying the hypotenuse in right-angled triangles",
            "2.2 Pythagoras' theorem: c^2 = a^2 + b^2",
            "2.3 Calculating the length of the hypotenuse",
            "2.4 Calculating the length of a shorter side",
            "2.5 Pythagorean triads and testing for right angles",
            "2.6 Practical 2D applications of Pythagoras' theorem"
        ],
        "3. Percentages, Ratios and Rates": [
            "3.1 Ratio concepts and simplifying ratios",
            "3.2 Dividing a quantity in a given ratio",
            "3.3 Unit rates, constant speed and unit pricing",
            "3.4 Percentage increase and decrease and finding original quantity",
            "3.5 Profit, loss and percentage profit/loss",
            "3.6 Simple interest formula: I = Prt"
        ],
        "4. Algebraic Techniques and Equations": [
            "4.1 Simplifying expressions by collecting like terms",
            "4.2 Index laws applied to algebraic terms",
            "4.3 Expanding single brackets using the distributive property",
            "4.4 Expanding and simplifying expressions with multiple brackets",
            "4.5 Factorising algebraic expressions by finding the HCF",
            "4.6 Solving two-step linear equations",
            "4.7 Equations with pronumerals on both sides and brackets"
        ],
        "5. Geometry, Angles and Polygons": [
            "5.1 Angle proofs on parallel lines and transversals",
            "5.2 Angle sum and exterior angle theorem of triangles",
            "5.3 Interior and exterior angles of polygons",
            "5.4 Congruent triangle tests: SSS, SAS, AAS, RHS",
            "5.5 Formal geometric congruence proofs"
        ],
        "6. Area, Surface Area and Volume": [
            "6.1 Perimeter and area of composite 2D shapes",
            "6.2 Surface area of rectangular and triangular prisms",
            "6.3 Volume of right prisms (V = Ah)",
            "6.4 Surface area of cylinders: SA = 2*pi*r^2 + 2*pi*r*h",
            "6.5 Volume of cylinders: V = pi*r^2*h",
            "6.6 Units of volume, capacity and conversions"
        ],
        "7. Linear Relationships and Graphs": [
            "7.1 Finding the gradient of a straight line: rise over run",
            "7.2 Finding the gradient using formula m = (y2 - y1) / (x2 - x1)",
            "7.3 The gradient-intercept form: y = mx + c",
            "7.4 Graphing straight lines using intercepts",
            "7.5 Horizontal and vertical lines: y = c, x = k",
            "7.6 Distance-time graphs and travel rate interpretation"
        ],
        "8. Probability and Data Analysis": [
            "8.1 Sample spaces for two-step experiments",
            "8.2 Tree diagrams and probability tables",
            "8.3 Probability with and without replacement",
            "8.4 Grouped frequency distribution tables",
            "8.5 Grouped data histograms and frequency polygons",
            "8.6 Mean, median, mode and range for grouped data"
        ]
    },
    "Year 9": {
        "1. Financial Mathematics": [
            "1.1 Wages, salaries, overtime and penalty rates",
            "1.2 Commission, piecework and royalties",
            "1.3 Taxable income, allowable deductions and tax brackets",
            "1.4 Simple interest loans and flat rate investments",
            "1.5 Compound interest formula: A = P(1 + r)^n",
            "1.6 Calculating future value and interest earned over time"
        ],
        "2. Indices and Surds": [
            "2.1 Review of index laws with integer exponents",
            "2.2 Negative indices: a^(-n) = 1 / a^n",
            "2.3 Fractional indices and radical form: a^(1/n) = sqrt[n](a)",
            "2.4 Simplifying surds and extracting square factors",
            "2.5 Adding and subtracting like surds",
            "2.6 Multiplying, dividing and expanding brackets with surds",
            "2.7 Rationalising the denominator"
        ],
        "3. Algebraic Expressions and Trinomials": [
            "3.1 Expanding binomial products: (a + b)(c + d)",
            "3.2 Special binomial expansions: perfect squares and difference of squares",
            "3.3 Factorising by taking out common factors",
            "3.4 Factorising by grouping in pairs",
            "3.5 Factorising monic quadratic trinomials: x^2 + bx + c",
            "3.6 Factorising non-monic quadratics: ax^2 + bx + c",
            "3.7 Operations on algebraic fractions"
        ],
        "4. Equations, Formulas and Inequalities": [
            "4.1 Solving complex linear equations with brackets and fractions",
            "4.2 Rearranging formulas and changing the subject",
            "4.3 Solving linear inequalities and number line representation",
            "4.4 Solving quadratic equations using the null factor law",
            "4.5 Solving quadratics by completing the square and quadratic formula"
        ],
        "5. Coordinate Geometry and Linear Relations": [
            "5.1 Distance between two points: d = sqrt((x2 - x1)^2 + (y2 - y1)^2)",
            "5.2 Midpoint of a segment: M = ((x1 + x2)/2, (y1 + y2)/2)",
            "5.3 Gradient of a straight line: m = (y2 - y1) / (x2 - x1)",
            "5.4 Gradient-intercept form: y = mx + c",
            "5.5 Point-gradient form: y - y1 = m(x - x1)",
            "5.6 General form: Ax + By + C = 0",
            "5.7 Parallel lines (m1 = m2) and perpendicular lines (m1 * m2 = -1)"
        ],
        "6. Trigonometry": [
            "6.1 Naming sides in a right triangle and trigonometric definitions",
            "6.2 Calculating unknown side lengths using sin, cos, tan",
            "6.3 Calculating unknown angles using inverse trig",
            "6.4 Angles of elevation and depression",
            "6.5 Three-figure compass bearings and navigational problems",
            "6.6 Trigonometry in multi-step 2D problems"
        ],
        "7. Surface Area and Volume": [
            "7.1 Surface area of right prisms and cylinders",
            "7.2 Volume of right prisms and cylinders",
            "7.3 Surface area of right pyramids and cones",
            "7.4 Volume of pyramids and cones",
            "7.5 Surface area and volume of spheres and hemispheres"
        ],
        "8. Non-Linear Relationships": [
            "8.1 Graphing parabolas: y = ax^2 + c and features",
            "8.2 Graphing parabolas: y = a(x - h)^2 + k",
            "8.3 Graphing hyperbolas: y = k / x and asymptotes",
            "8.4 Graphing circles: x^2 + y^2 = r^2",
            "8.5 Graphing exponential functions: y = a^x"
        ],
        "9. Probability and Statistics": [
            "9.1 Multi-stage probability tree diagrams and arrays",
            "9.2 Independent vs dependent events and sampling without replacement",
            "9.3 Conditional probability in Venn diagrams and two-way tables",
            "9.4 Five-number summary, quartiles and interquartile range (IQR)",
            "9.5 Parallel box plots and identifying outliers",
            "9.6 Bivariate scatter plots, correlation and lines of best fit"
        ]
    },
    "Year 10": {
        "1. Consumer Arithmetic and Financial Mathematics": [
            "1.1 Compound interest calculations and formula: A = P(1 + r)^n",
            "1.2 Fractional compounding periods (monthly, quarterly, daily)",
            "1.3 Straight-line and declining-balance asset depreciation",
            "1.4 Credit card interest, repayments and personal loans",
            "1.5 Comparing superannuation growth and investment options"
        ],
        "2. Surds, Indices and Logarithms (Advanced)": [
            "2.1 Review of index laws with negative and fractional exponents",
            "2.2 Advanced operations with surds and binomial rationalisation",
            "2.3 Introduction to logarithms: converting between index and logarithmic form",
            "2.4 Logarithmic laws and simplifications",
            "2.5 Solving exponential equations using logarithms"
        ],
        "3. Quadratic Expressions and Equations (Advanced)": [
            "3.1 Factorising complex quadratic expressions",
            "3.2 Solving quadratic equations by completing the square and quadratic formula",
            "3.3 The discriminant Delta = b^2 - 4ac and nature of roots",
            "3.4 Parabola vertex form: y = a(x - h)^2 + k and finding intercepts",
            "3.5 Maximum and minimum quadratic optimization word problems",
            "3.6 Simultaneous equations involving one linear and one quadratic equation"
        ],
        "4. Coordinate Geometry and Linear Systems": [
            "4.1 Gradient-intercept form, general form and line equations",
            "4.2 Parallel and perpendicular lines and their properties",
            "4.3 Solving simultaneous equations graphically",
            "4.4 Solving simultaneous equations algebraically: substitution and elimination",
            "4.5 Applications of simultaneous equations in problem solving"
        ],
        "5. Further Trigonometry": [
            "5.1 Trigonometry in 3D right-angled situations",
            "5.2 Navigational bearings and multi-triangle problems",
            "5.3 Angles of any magnitude and ASTC quadrant signs",
            "5.4 The Sine Rule for finding sides and angles",
            "5.5 The ambiguous case of the Sine Rule",
            "5.6 The Cosine Rule for finding sides and angles",
            "5.7 Area of any triangle: Area = 1/2 * a * b * sin(C)"
        ],
        "6. Surface Area and Volume": [
            "6.1 Surface area of composite 3D solids",
            "6.2 Volume of composite 3D solids",
            "6.3 Truncated pyramids and cones (frustums)",
            "6.4 Limits of accuracy, absolute error and percentage error"
        ],
        "7. Circle Geometry (Advanced)": [
            "7.1 Circle anatomy: chords, tangents, secants, cyclic polygons",
            "7.2 Chords of a circle: perpendicular bisector theorem and equal chords",
            "7.3 Angle at centre is twice angle at circumference",
            "7.4 Angles in the same segment and angle in a semicircle",
            "7.5 Cyclic quadrilaterals and supplementary opposite angles",
            "7.6 Tangents from an external point and radius-tangent perpendicularity",
            "7.7 The Alternate Segment Theorem"
        ],
        "8. Curve Sketching and Polynomials (Advanced)": [
            "8.1 Function definition, function notation and vertical line test",
            "8.2 Domain and range of functions in interval notation",
            "8.3 Graphing cubic functions and transformations",
            "8.4 Graphing circles, semi-circles and hyperbolas",
            "8.5 Polynomial long division and synthetic division",
            "8.6 The Remainder Theorem and Factor Theorem"
        ],
        "9. Probability and Statistics": [
            "9.1 Bivariate scatter plots and interpreting associations",
            "9.2 Pearson's correlation coefficient r and strength of relationship",
            "9.3 The line of best fit and making predictions (interpolation vs extrapolation)",
            "9.4 Correlation vs causation and confounding variables",
            "9.5 Standard deviation and spread of data distributions"
        ]
    }
}

MATHSCAPE_CURRICULUM["Year 9 (Standard)"] = MATHSCAPE_CURRICULUM["Year 9"]
MATHSCAPE_CURRICULUM["Year 9 (Advanced)"] = MATHSCAPE_CURRICULUM["Year 9"]
MATHSCAPE_CURRICULUM["Year 10 (Standard)"] = MATHSCAPE_CURRICULUM["Year 10"]
MATHSCAPE_CURRICULUM["Year 10 (Advanced)"] = MATHSCAPE_CURRICULUM["Year 10"]
