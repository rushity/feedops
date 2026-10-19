"""Demo data seeding service for development, testing, and UI demonstration.

Populates realistic, deterministic fictional data across all FeedOps entities:
- 1 Admin user
- 5 Merchant partners (Electronics, Fashion, Home, Books, Fitness)
- 25 Consumer users with rich profiles, preferences, and consents
- 100 Realistic products (in INR) across 5 categories
- 12 Feeds & 60 Articles with realistic summaries and categories
- Consumer interactions: saved items, feedback, dismissals, price alerts
- 30 Notifications & notification preferences
- 30 Affiliate clicks & 8 converted orders
- 9 Merchant campaigns across pending, active, completed, suspended, rejected states
- Merchant import jobs & platform audit logs

Guarantees:
- Safe, non-destructive, and 100% idempotent.
- Uses fixed random seed (42) for reproducible data generation.
- All email addresses use the reserved domain 'example.com'.
- No real credentials, payments, external HTTP requests, or emails.
- Optional --reset-demo removes only demo-tagged records.
"""

from datetime import datetime, timedelta, timezone
import json
import random
from werkzeug.security import generate_password_hash

# Fixed seed for reproducibility
RANDOM_SEED = 42

# Demonstration credentials (DEVELOPMENT ONLY)
ADMIN_CREDENTIALS = {
    "email": "admin@example.com",
    "password": "AdminDemo2026!",
    "role": "admin",
    "display_name": "Dev Platform Administrator",
    "phone": "+91 98765 00001",
}

MERCHANT_CREDENTIALS = [
    {
        "email": "merchant.electronics@example.com",
        "password": "MerchantDemo2026!",
        "role": "merchant",
        "display_name": "Apex Electronics Merchant",
        "phone": "+91 98765 10001",
        "partner": {
            "business_name": "Apex Electronics",
            "website": "https://apex-electronics.example.com",
            "business_email": "contact@apex-electronics.example.com",
            "category": "electronics",
            "status": "approved",
            "sku_prefix": "APEX",
        },
    },
    {
        "email": "merchant.fashion@example.com",
        "password": "MerchantDemo2026!",
        "role": "merchant",
        "display_name": "Luxe Trendwear Merchant",
        "phone": "+91 98765 10002",
        "partner": {
            "business_name": "Luxe Trendwear",
            "website": "https://luxe-fashion.example.com",
            "business_email": "contact@luxe-fashion.example.com",
            "category": "fashion",
            "status": "approved",
            "sku_prefix": "LUXE",
        },
    },
    {
        "email": "merchant.home@example.com",
        "password": "MerchantDemo2026!",
        "role": "merchant",
        "display_name": "Urban Nest Living Merchant",
        "phone": "+91 98765 10003",
        "partner": {
            "business_name": "Urban Nest Living",
            "website": "https://urbannest.example.com",
            "business_email": "contact@urbannest.example.com",
            "category": "home",
            "status": "approved",
            "sku_prefix": "NEST",
        },
    },
    {
        "email": "merchant.books@example.com",
        "password": "MerchantDemo2026!",
        "role": "merchant",
        "display_name": "Horizon Books Merchant",
        "phone": "+91 98765 10004",
        "partner": {
            "business_name": "Horizon Books & Edu",
            "website": "https://horizonbooks.example.com",
            "business_email": "contact@horizonbooks.example.com",
            "category": "learning",
            "status": "approved",
            "sku_prefix": "BOOK",
        },
    },
    {
        "email": "merchant.fitness@example.com",
        "password": "MerchantDemo2026!",
        "role": "merchant",
        "display_name": "Velocity Athletics Merchant",
        "phone": "+91 98765 10005",
        "partner": {
            "business_name": "Velocity Athletics",
            "website": "https://velocity-athletics.example.com",
            "business_email": "contact@velocity-athletics.example.com",
            "category": "sports",
            "status": "approved",
            "sku_prefix": "VELO",
        },
    },
]

CONSUMER_PROFILES = [
    ("Aarav Sharma", ["electronics", "learning"], 2000, 50000, ["Apple", "Sony", "Logitech"]),
    ("Priya Patel", ["fashion", "lifestyle"], 1000, 25000, ["Luxe", "Zara", "Nike"]),
    ("Rohan Mehta", ["electronics", "sports"], 3000, 75000, ["Apex", "Apple", "Puma"]),
    ("Ananya Iyer", ["learning", "home"], 500, 15000, ["Horizon", "Penguin", "UrbanNest"]),
    ("Vikram Singh", ["sports", "fitness"], 1500, 40000, ["Velocity", "Nike", "Adidas"]),
    ("Neha Gupta", ["fashion", "home"], 1200, 30000, ["Luxe", "UrbanNest", "H&M"]),
    ("Kavita Reddy", ["electronics", "home"], 5000, 90000, ["Philips", "Dyson", "Sony"]),
    ("Arjun Nair", ["learning", "electronics"], 1000, 60000, ["O'Reilly", "Logitech", "Apex"]),
    ("Pooja Verma", ["fashion", "sports"], 800, 20000, ["Puma", "Luxe", "UnderArmour"]),
    ("Siddharth Rao", ["electronics", "gaming"], 4000, 120000, ["Sony", "Apex", "Samsung"]),
    ("Divya Menon", ["home", "lifestyle"], 2000, 35000, ["UrbanNest", "IKEA", "Philips"]),
    ("Aditya Joshi", ["sports", "learning"], 1000, 30000, ["Velocity", "Horizon", "Nike"]),
    ("Meera Sen", ["books", "learning"], 400, 10000, ["Penguin", "HarperCollins", "Horizon"]),
    ("Karan Malhotra", ["electronics", "fashion"], 2500, 70000, ["Apple", "Luxe", "Apex"]),
    ("Rhea Kapoor", ["lifestyle", "fashion"], 1500, 45000, ["Luxe", "Zara", "UrbanNest"]),
    ("Sanjay Bhat", ["home", "electronics"], 3000, 80000, ["Dyson", "Philips", "Samsung"]),
    ("Deepa Deshmukh", ["learning", "sports"], 1000, 25000, ["Horizon", "Velocity", "Decathlon"]),
    ("Nikhil Chawla", ["electronics", "audio"], 2000, 55000, ["Sony", "Bose", "Apex"]),
    ("Tarun Saxena", ["fitness", "lifestyle"], 1500, 35000, ["Velocity", "Nike", "UrbanNest"]),
    ("Shreya Das", ["fashion", "books"], 800, 18000, ["Luxe", "Penguin", "FabIndia"]),
    ("Varun Aggarwal", ["electronics", "smart_home"], 4000, 95000, ["Philips", "Apex", "Google"]),
    ("Ishaan Roy", ["sports", "outdoor"], 2000, 50000, ["Velocity", "Puma", "Garmin"]),
    ("Tanvi Kulkarni", ["home", "kitchen"], 1500, 40000, ["UrbanNest", "Philips", "Prestige"]),
    ("Mohit Pandey", ["learning", "coding"], 600, 20000, ["O'Reilly", "Horizon", "Packt"]),
    ("Zoya Khan", ["lifestyle", "wellness"], 1200, 30000, ["UrbanNest", "Velocity", "Luxe"]),
]

DEMO_FEEDS = [
    {
        "url": "https://example.com/demo-feeds/tech-trends.xml",
        "title": "Tech Trends & Computing Innovations",
        "status": "ok",
        "category": "technology",
    },
    {
        "url": "https://example.com/demo-feeds/ai-breakthroughs.xml",
        "title": "Artificial Intelligence & Robotics Wire",
        "status": "ok",
        "category": "technology",
    },
    {
        "url": "https://example.com/demo-feeds/gadget-daily.xml",
        "title": "The Daily Gadget & Consumer Electronics",
        "status": "ok",
        "category": "technology",
    },
    {
        "url": "https://example.com/demo-feeds/fashion-forward.xml",
        "title": "Fashion Forward & Modern Apparel",
        "status": "ok",
        "category": "fashion",
    },
    {
        "url": "https://example.com/demo-feeds/style-and-living.xml",
        "title": "Contemporary Style & Lifestyle Journal",
        "status": "ok",
        "category": "lifestyle",
    },
    {
        "url": "https://example.com/demo-feeds/home-decor-weekly.xml",
        "title": "Home Living & Interior Architecture Weekly",
        "status": "ok",
        "category": "home",
    },
    {
        "url": "https://example.com/demo-feeds/smart-living.xml",
        "title": "Smart Home, Clean Energy & Eco Living",
        "status": "ok",
        "category": "home",
    },
    {
        "url": "https://example.com/demo-feeds/book-chronicle.xml",
        "title": "The Literary Chronicle & Non-Fiction Reviews",
        "status": "ok",
        "category": "learning",
    },
    {
        "url": "https://example.com/demo-feeds/tech-education.xml",
        "title": "Software Engineering & Continuous Learning",
        "status": "ok",
        "category": "learning",
    },
    {
        "url": "https://example.com/demo-feeds/fitness-digest.xml",
        "title": "Athletics, Endurance & Strength Digest",
        "status": "ok",
        "category": "sports",
    },
    {
        "url": "https://example.com/demo-feeds/wellness-today.xml",
        "title": "Holistic Health, Recovery & Nutrition Today",
        "status": "ok",
        "category": "sports",
    },
    {
        "url": "https://example.com/demo-feeds/retail-wire.xml",
        "title": "Global Commerce & Supply Chain Monitor",
        "status": "error",
        "category": "business",
        "error": "Upstream source temporarily unavailable (simulated demo status)",
    },
]

# Raw product catalogue specs (20 products per partner = 100 total)
ELECTRONICS_PRODUCTS = [
    ("Apex Phone 15 Pro Max 256GB", "Flagship smartphone featuring aerospace titanium chassis, ProMotion 120Hz OLED, and next-generation computational photography.", "electronics", "Apex", 79999.0, "in_stock", "approved"),
    ("Apex Phone 15 128GB", "Supercharged everyday smartphone with dynamic ceramic shield and all-day battery efficiency.", "electronics", "Apex", 54999.0, "in_stock", "approved"),
    ("Apex Book Air M3 13.6-inch", "Ultra-thin laptop with silent fanless architecture, Retina display, and 18-hour continuous battery endurance.", "electronics", "Apex", 84999.0, "in_stock", "approved"),
    ("Apex Book Pro Studio 16-inch", "Workstation-grade powerhouse laptop engineered for 3D creators, developers, and data scientists.", "electronics", "Apex", 149999.0, "in_stock", "approved"),
    ("NoiseCancel 750 Wireless Headphones", "Industry-leading active noise cancellation with spatial high-resolution audio codecs and 40h battery.", "electronics", "Sony", 24999.0, "in_stock", "approved"),
    ("TrueWireless BassPod Earbuds", "Compact ergonomic earbuds with dual beamforming microphones, IPX5 sweat resistance, and Qi charging.", "electronics", "Sony", 7999.0, "in_stock", "approved"),
    ("Mechanical Tactile Keyboard RGB", "Aircraft-grade aluminum mechanical keyboard with hot-swappable switches and per-key RGB backlighting.", "electronics", "Logitech", 6499.0, "in_stock", "approved"),
    ("Master Precision Wireless Mouse 3S", "Ergonomic productivity mouse with electromagnetic scroll wheel and silent acoustic switches.", "electronics", "Logitech", 7999.0, "in_stock", "approved"),
    ("UltraWide 34-inch Curved Monitor", "34-inch WQHD curved IPS gaming and productivity monitor with 144Hz refresh rate and USB-C 90W delivery.", "electronics", "Samsung", 42999.0, "in_stock", "approved"),
    ("Smart 4K UHD OLED TV 55-inch", "Self-lit OLED pixels delivering infinite contrast, Dolby Vision HDR, and immersive gaming VRR mode.", "electronics", "Sony", 89999.0, "in_stock", "approved"),
    ("Apex SmartWatch Series 9", "Comprehensive health tracking companion with ECG monitor, blood oxygen sensors, and sleep score diagnostics.", "electronics", "Apex", 29999.0, "in_stock", "approved"),
    ("FastCharge 100W GaN 4-Port Hub", "Ultra-compact gallium nitride wall charger with dual USB-C Power Delivery and surge protection.", "electronics", "Apex", 3499.0, "in_stock", "approved"),
    ("Portable SSD Rugged 1TB", "High-speed USB 3.2 Gen 2 portable solid-state drive with 1050MB/s transfer rates and drop resistance.", "electronics", "Samsung", 8499.0, "in_stock", "approved"),
    ("Full HD Streaming Webcam Pro", "Auto-focusing 1080p 60fps video camera with integrated stereo microphones and privacy shutter.", "electronics", "Logitech", 4999.0, "in_stock", "approved"),
    ("Bluetooth Conference Speakerphone", "Omnidirectional 360-degree microphone array with acoustic echo cancellation for crystal-clear calls.", "electronics", "Sony", 6999.0, "in_stock", "approved"),
    ("MagSafe Wireless Power Bank 10000mAh", "Magnetic snap-on power bank with bidirectional fast charging and LED charge percentage readout.", "electronics", "Apex", 2999.0, "in_stock", "approved"),
    ("Ergonomic Monitor Desk Arm Dual", "Heavy-duty gas spring dual monitor mount with cable management channels and 360-degree rotation.", "electronics", "Logitech", 4299.0, "in_stock", "approved"),
    ("Apex Phone 16 Vision Edition", "Next-generation spatial capture smartphone with neural engine acceleration.", "electronics", "Apex", 99999.0, "preorder", "approved"),
    ("Apex Foldable Duo Tablet", "Experimental dual-hinge folding tablet concept currently undergoing platform moderation.", "electronics", "Apex", 119999.0, "in_stock", "pending"),
    ("Uncertified Laser Projector 8K", "Imported laser projector flagged for missing technical regulatory compliance documentation.", "electronics", "Apex", 35000.0, "out_of_stock", "rejected"),
]

FASHION_PRODUCTS = [
    ("Oxford Cotton Slim Button-Down Shirt", "Tailored premium long-staple cotton shirt suitable for formal office wear and casual weekends.", "fashion", "Luxe", 2499.0, "in_stock", "approved"),
    ("Merino Wool Crewneck Sweater", "Extra-fine breathable Australian merino wool pullover offering thermal regulation and softness.", "fashion", "Luxe", 3999.0, "in_stock", "approved"),
    ("Stretch Selvage Denim Jeans", "Classic 5-pocket denim woven with 1% elastane for flexible movement and durable indigo dye retention.", "fashion", "Levi's", 3499.0, "in_stock", "approved"),
    ("Tailored Structured Blazer Navy", "Modern slim-silhouette blazer crafted from wool blend with notched lapels and horn buttons.", "fashion", "Luxe", 7999.0, "in_stock", "approved"),
    ("Water-Repellent Commuter Trench", "Minimalist double-breasted trench coat with storm flap and eco-friendly fluorocarbon-free finish.", "fashion", "Luxe", 8999.0, "in_stock", "approved"),
    ("Handcrafted Leather Chelsea Boots", "Goodyear-welted full-grain leather boots with elastic side gussets and cushioned leather insoles.", "fashion", "Luxe", 6999.0, "in_stock", "approved"),
    ("Minimalist Court Sneaker White", "Monochrome Italian Nappa leather sneakers with vulcanized rubber cupsole and memory foam footbed.", "fashion", "Luxe", 4499.0, "in_stock", "approved"),
    ("Supima Cotton T-Shirt 3-Pack", "Ultra-soft combed Supima cotton crewneck tees designed to hold shape through continuous washes.", "fashion", "Luxe", 1999.0, "in_stock", "approved"),
    ("Pleated Linen Summer Trousers", "Lightweight airy European flax linen trousers with relaxed taper and drawstring waistband.", "fashion", "Luxe", 3299.0, "in_stock", "approved"),
    ("Cashmere Ribbed Knit Scarf", "Luxurious 100% Mongolian cashmere scarf providing cozy warmth without excess bulk.", "fashion", "Luxe", 2999.0, "in_stock", "approved"),
    ("Full-Grain Leather Dress Belt", "Vegetable-tanned leather belt with polished brushed nickel buckle and beveled edge detailing.", "fashion", "Luxe", 1499.0, "in_stock", "approved"),
    ("Waterproof Everyday Backpack 20L", "Weatherproof coated canvas commuter pack with dedicated 16-inch padded laptop compartment.", "fashion", "Luxe", 3999.0, "in_stock", "approved"),
    ("Chino Casual Trousers Khaki", "Versatile stretch-cotton twill chinos with clean front pockets and garment-washed finish.", "fashion", "Zara", 2299.0, "in_stock", "approved"),
    ("Polarized Classic Acetate Sunglasses", "Handcrafted acetate frames with UV400 polarized scratch-resistant lenses.", "fashion", "Luxe", 2799.0, "in_stock", "approved"),
    ("Thermal Fleece Zip Jacket", "Cozy high-pile fleece jacket with zip chest pocket and reinforced elbow patches.", "fashion", "Luxe", 3499.0, "in_stock", "approved"),
    ("Silk Patterned Pocket Square Set", "Pure mulberry silk hand-rolled pocket squares in assorted classic geometric designs.", "fashion", "Luxe", 999.0, "in_stock", "approved"),
    ("Leather Bi-Fold RFID Wallet", "Slim bifold wallet with eight card slots, cash divider, and integrated RFID protection.", "fashion", "Luxe", 1299.0, "in_stock", "approved"),
    ("Luxe Haute Couture Wool Overcoat", "Exclusive limited-run double-faced cashmere and wool overcoat releasing next month.", "fashion", "Luxe", 18999.0, "preorder", "approved"),
    ("Silk Blend Festive Kurta Set", "Embroidered festive celebratory attire awaiting final merchant catalogue validation.", "fashion", "Luxe", 4999.0, "in_stock", "pending"),
    ("Counterfeit Designer Monogram Belt", "Catalogue submission rejected due to intellectual property trademark dispute.", "fashion", "Luxe", 1200.0, "out_of_stock", "rejected"),
]

HOME_PRODUCTS = [
    ("Smart HEPA Air Purifier Pro", "True HEPA filtration capturing 99.97% of airborne particles with real-time PM2.5 air quality display.", "home", "Philips", 14999.0, "in_stock", "approved"),
    ("Robotic Vacuum & Sonic Mop X1", "Laser LiDAR navigation vacuum with automated empty station and high-frequency scrub mop pads.", "home", "UrbanNest", 34999.0, "in_stock", "approved"),
    ("Ergonomic Memory Foam Pillow", "Contoured cervical orthopedic neck support pillow with cooling gel breathable outer mesh.", "home", "UrbanNest", 1999.0, "in_stock", "approved"),
    ("All-Season Microfiber Comforter", "Hypoallergenic down-alternative duvet insert with baffle-box stitching for even warmth distribution.", "home", "UrbanNest", 2999.0, "in_stock", "approved"),
    ("Smart Ambient Sunset Floor Lamp", "Color-tunable RGBW architectural floor lamp compatible with voice assistants and app automations.", "home", "Philips", 5499.0, "in_stock", "approved"),
    ("Cast Iron Dutch Oven 5.5 Quart", "Heavyweight enameled cast iron pot with tight-fitting lid for slow stews, braises, and sourdough baking.", "home", "UrbanNest", 4999.0, "in_stock", "approved"),
    ("Precision Temperature Pour-Over Kettle", "Gooseneck stainless steel electric kettle with 1-degree temperature dial and 60-minute keep-warm mode.", "home", "UrbanNest", 3799.0, "in_stock", "approved"),
    ("Cold Press Masticating Juicer", "Slow-rpm quiet auger juicer yielding maximum nutrient and enzymatic juice extraction.", "home", "Philips", 8999.0, "in_stock", "approved"),
    ("Handcrafted Ceramic Dinnerware 16-Piece", "Artisan stoneware collection including dinner plates, salad plates, cereal bowls, and mugs.", "home", "UrbanNest", 4499.0, "in_stock", "approved"),
    ("Bamboo Fiber Bathroom Towel Set", "Ultra-absorbent 650 GSM plush bath sheet and hand towel bundle woven from organic bamboo rayon.", "home", "UrbanNest", 1799.0, "in_stock", "approved"),
    ("Standing Desk Dual Motor Frame", "Heavy-gauge steel electric height-adjustable desk frame with anti-collision safety sensors.", "home", "UrbanNest", 18999.0, "in_stock", "approved"),
    ("Ergonomic Mesh Task Chair", "Breathable mesh executive office chair with adjustable 3D armrests and pneumatic lumbar support.", "home", "UrbanNest", 12999.0, "in_stock", "approved"),
    ("Ultrasonic Aromatherapy Essential Oil Diffuser", "Whisper-quiet 500ml ultrasonic cool mist humidifier with timer settings and ambient nightlight.", "home", "UrbanNest", 1499.0, "in_stock", "approved"),
    ("Digital Kitchen Food Scale High-Precision", "Stainless steel platform weighing up to 10kg with 1g graduation and convenient tare function.", "home", "UrbanNest", 899.0, "in_stock", "approved"),
    ("Stainless Steel Knife Block Set 7-Piece", "High-carbon German steel kitchen knives with ergonomic handles and acacia wood storage block.", "home", "UrbanNest", 5999.0, "in_stock", "approved"),
    ("Cordless Stick Vacuum V12", "Powerful brushless motor stick vacuum with illuminated laser dust detection and 60min runtime.", "home", "Dyson", 39999.0, "in_stock", "approved"),
    ("Modular Indoor Hydroponic Herb Garden", "Smart countertop herb cultivator with automated LED grow lighting schedule and water pump.", "home", "UrbanNest", 3499.0, "in_stock", "approved"),
    ("UrbanNest Smart Climate Hub V3", "Next-gen Matter-compatible climate hub with humidity and CO2 regulation modules.", "home", "UrbanNest", 6999.0, "preorder", "approved"),
    ("Smart Espresso Machine Dual Boiler", "Professional grade commercial pump home espresso machine pending energy star rating review.", "home", "UrbanNest", 48000.0, "in_stock", "pending"),
    ("Unregulated Ionizing Ozone Generator", "Product rejected due to consumer health warning guidelines regarding ozone emissions.", "home", "UrbanNest", 6500.0, "out_of_stock", "rejected"),
]

BOOK_PRODUCTS = [
    ("Designing Data-Intensive Applications", "The definitive guide to distributed architectures, consensus protocols, and storage engine fundamentals.", "learning", "O'Reilly", 1899.0, "in_stock", "approved"),
    ("Clean Architecture & Domain Patterns", "A craftsman's guide to software structure, dependency inversion, and maintainable enterprise systems.", "learning", "Horizon", 1499.0, "in_stock", "approved"),
    ("The Psychology of Money", "Timeless lessons on wealth, greed, and happiness by Morgan Housel exploring behavioral finance.", "learning", "Penguin", 399.0, "in_stock", "approved"),
    ("Atomic Habits: Proven Framework", "James Clear's transformative handbook on small changes, habit stacking, and identity-based improvement.", "learning", "Penguin", 499.0, "in_stock", "approved"),
    ("Deep Learning with Python 2nd Edition", "Practical neural networks and generative AI implementations by Keras creator Francois Chollet.", "learning", "Horizon", 2299.0, "in_stock", "approved"),
    ("Database Internals: Distributed Systems", "A deep technical dive into how modern distributed databases store, replicate, and query data at scale.", "learning", "O'Reilly", 2199.0, "in_stock", "approved"),
    ("Thinking, Fast and Slow", "Nobel laureate Daniel Kahneman's foundational exploration of intuitive versus analytical thought.", "learning", "Penguin", 599.0, "in_stock", "approved"),
    ("System Design Interview Guide Vol 1 & 2", "In-depth case studies on scaling web infrastructure, message queues, rate limiters, and distributed storage.", "learning", "Horizon", 2499.0, "in_stock", "approved"),
    ("Sapiens: A Brief History of Humankind", "Yuval Noah Harari's acclaimed journey through humanity's evolutionary, cognitive, and scientific leaps.", "learning", "HarperCollins", 499.0, "in_stock", "approved"),
    ("Zero to One: Notes on Startups", "Peter Thiel's insights on vertical progress, monopoly defensibility, and building transformative tech companies.", "learning", "Penguin", 450.0, "in_stock", "approved"),
    ("Hands-On Machine Learning with Scikit-Learn & PyTorch", "Comprehensive practical guide to gradient boosting, deep vision models, transformers, and deployment.", "learning", "O'Reilly", 2699.0, "in_stock", "approved"),
    ("Refactoring: Improving Code Design", "Martin Fowler's classic text providing catalogued step-by-step transformations for legacy codebases.", "learning", "Horizon", 1799.0, "in_stock", "approved"),
    ("Man's Search for Meaning", "Viktor E. Frankl's profoundly moving psychological chronicle of purpose and resilience.", "learning", "Penguin", 299.0, "in_stock", "approved"),
    ("The Pragmatic Programmer: 20th Anniversary", "Essential guidance for software developers spanning tooling, career craft, and engineering discipline.", "learning", "Horizon", 1650.0, "in_stock", "approved"),
    ("Modern Indian History & Polity Handbook", "Comprehensive reference manual for competitive examinations and civil services preparation.", "learning", "Horizon", 850.0, "in_stock", "approved"),
    ("Oxford World Atlas & Physical Geography", "Full-color cartographic reference containing detailed topographic surveys, climate data, and socio-economic maps.", "learning", "Horizon", 1250.0, "in_stock", "approved"),
    ("Financial Accounting & Corporate Valuation", "Practical valuation guide to discounted cash flow models, balance sheet analysis, and LBO transactions.", "learning", "Horizon", 1150.0, "in_stock", "approved"),
    ("Generative Agents & LLM Architectures 2026", "Pre-order upcoming textbook on autonomous multi-agent systems and symbolic reasoning frameworks.", "learning", "Horizon", 2999.0, "preorder", "approved"),
    ("Algorithmic Trading & High-Frequency Systems", "Pending moderation check for proprietary technical source code inclusions.", "learning", "Horizon", 3200.0, "in_stock", "pending"),
    ("Pirated Exam Question Bank Dumps", "Flagged and rejected submission violating education copyright and testing integrity rules.", "learning", "Horizon", 500.0, "out_of_stock", "rejected"),
]

SPORTS_PRODUCTS = [
    ("Velocity Cast-Iron Kettlebell 16kg", "Solid cast-iron bell with wide textured grip handle and flat machined base for stable floor work.", "sports", "Velocity", 2499.0, "in_stock", "approved"),
    ("Velocity Cast-Iron Kettlebell 24kg", "Heavyweight cast-iron kettlebell powder-coated for corrosion resistance and chalk retention.", "sports", "Velocity", 3499.0, "in_stock", "approved"),
    ("Non-Slip Pro Alignment Yoga Mat 6mm", "High-density natural rubber and eco-polyurethane mat with etched central alignment laser guides.", "sports", "Velocity", 1999.0, "in_stock", "approved"),
    ("Resistance Loop Exercise Bands Set of 5", "Latex exercise loops ranging from extra-light to extra-heavy for mobility, glutes, and rehab.", "sports", "Velocity", 699.0, "in_stock", "approved"),
    ("Adjustable Aluminum Speed Jump Rope", "Dual-bearing high-velocity wire jump rope with knurled non-slip aluminum alloy handles.", "sports", "Velocity", 899.0, "in_stock", "approved"),
    ("HydroInsulated Sports Water Flask 1000ml", "Double-wall vacuum insulated stainless steel sports bottle keeping beverages cold for 24 hours.", "sports", "Velocity", 1299.0, "in_stock", "approved"),
    ("Nike Air Zoom Pegasus 40 Running Shoes", "Responsive engineered mesh road runners with dual Zoom Air units and durable waffle outsole.", "sports", "Nike", 8499.0, "in_stock", "approved"),
    ("Adidas Ultraboost Light Running Shoes", "Lightweight energetic running shoes featuring Boost midsole cushioning and Continental rubber grip.", "sports", "Adidas", 11999.0, "in_stock", "approved"),
    ("Foam Roller Deep Tissue Muscle Recovery 45cm", "High-density EVA foam cylinder with multi-density grid pattern for myofascial release.", "sports", "Velocity", 1199.0, "in_stock", "approved"),
    ("Adjustable Dumbbell Pair 2.5kg - 24kg", "Quick-turn dial selector dumbbells replacing 15 pairs of conventional free weights in compact rack.", "sports", "Velocity", 18999.0, "in_stock", "approved"),
    ("Puma Men's Training Track Pants", "Breathable dryCELL moisture-wicking athletic trousers with secure zip pockets and tapered ankles.", "sports", "Puma", 2299.0, "in_stock", "approved"),
    ("Gym Duffle Bag with Shoe Compartment 40L", "Water-resistant gym holdall featuring ventilated sneaker pocket and wet pouch for swim gear.", "sports", "Velocity", 1799.0, "in_stock", "approved"),
    ("Under Armour Compression Base Layer", "Ultra-tight second-skin compression shirt delivering muscle support and strategic mesh ventilation.", "sports", "UnderArmour", 2199.0, "in_stock", "approved"),
    ("Hand Grip Strengthener Adjustable 10-60kg", "Heavy-duty steel spring hand and forearm exerciser with ergonomic rubberized non-slip grip.", "sports", "Velocity", 449.0, "in_stock", "approved"),
    ("Percussion Deep Tissue Massage Gun", "Quiet brushless motor massager with 5 speed levels and 6 interchangeable muscle therapy attachments.", "sports", "Velocity", 5499.0, "in_stock", "approved"),
    ("Whey Protein Isolate 100% Unflavored 1kg", "Ultra-pure cross-flow microfiltered whey isolate providing 27g protein and zero added sugar per serving.", "sports", "Velocity", 2999.0, "in_stock", "approved"),
    ("Hydration Electrolyte Powder Box of 30", "Balanced sodium, potassium, and magnesium single-serve drink mix with zero sugar and natural citrus.", "sports", "Velocity", 999.0, "in_stock", "approved"),
    ("Velocity Smart Carbon Road Bike", "Ultra-light carbon fiber frame road bicycle with electronic shifting groupset currently open for reserve.", "sports", "Velocity", 125000.0, "preorder", "approved"),
    ("Commercial Power Rack with Cable Pulley", "Heavy-gauge 3x3 steel commercial gym rig awaiting structural warehouse safety signoff.", "sports", "Velocity", 45000.0, "in_stock", "pending"),
    ("Banned Anabolic Pre-Workout Supplement", "Rejected catalogue entry containing prohibited pharmaceutical stimulants.", "sports", "Velocity", 2800.0, "out_of_stock", "rejected"),
]

PRODUCT_GROUPS = [
    ("APEX", ELECTRONICS_PRODUCTS),
    ("LUXE", FASHION_PRODUCTS),
    ("NEST", HOME_PRODUCTS),
    ("BOOK", BOOK_PRODUCTS),
    ("VELO", SPORTS_PRODUCTS),
]


def seed_all_demo_data(db) -> dict:
    """Populate full demo data set in a single safe, idempotent transaction."""
    random.seed(RANDOM_SEED)
    summary = {
        "users_created": 0,
        "users_existing": 0,
        "partners_created": 0,
        "partners_existing": 0,
        "products_created": 0,
        "products_existing": 0,
        "feeds_created": 0,
        "feeds_existing": 0,
        "articles_created": 0,
        "articles_existing": 0,
        "preferences_configured": 0,
        "saved_items_created": 0,
        "feedback_created": 0,
        "notifications_created": 0,
        "affiliate_clicks_created": 0,
        "campaigns_created": 0,
        "campaigns_existing": 0,
        "import_jobs_created": 0,
        "audit_logs_created": 0,
    }

    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. ADMIN USER
    admin_row = db.execute("SELECT id FROM users WHERE email = ?", (ADMIN_CREDENTIALS["email"],)).fetchone()
    if not admin_row:
        cur = db.execute(
            """INSERT INTO users (email, password_hash, role, display_name, phone, is_verified, status)
               VALUES (?, ?, ?, ?, ?, 1, 'active')""",
            (
                ADMIN_CREDENTIALS["email"],
                generate_password_hash(ADMIN_CREDENTIALS["password"]),
                ADMIN_CREDENTIALS["role"],
                ADMIN_CREDENTIALS["display_name"],
                ADMIN_CREDENTIALS["phone"],
            ),
        )
        admin_id = cur.lastrowid
        summary["users_created"] += 1
    else:
        admin_id = admin_row["id"]
        summary["users_existing"] += 1

    # Ensure admin preferences & notifications
    db.execute(
        """INSERT OR IGNORE INTO user_preferences (user_id, interests, budget_min, budget_max, preferred_brands, currency)
           VALUES (?, '["technology", "business"]', 0, 200000, '[]', 'INR')""",
        (admin_id,),
    )
    db.execute("INSERT OR IGNORE INTO notification_preferences (user_id) VALUES (?)", (admin_id,))
    db.execute(
        "INSERT OR IGNORE INTO consent_records (user_id, consent_type, granted) VALUES (?, 'terms_and_privacy', 1)",
        (admin_id,),
    )

    # 2. MERCHANTS & PARTNERS
    partner_id_map = {}
    for merch_spec in MERCHANT_CREDENTIALS:
        u_row = db.execute("SELECT id FROM users WHERE email = ?", (merch_spec["email"],)).fetchone()
        if not u_row:
            cur = db.execute(
                """INSERT INTO users (email, password_hash, role, display_name, phone, is_verified, status)
                   VALUES (?, ?, ?, ?, ?, 1, 'active')""",
                (
                    merch_spec["email"],
                    generate_password_hash(merch_spec["password"]),
                    merch_spec["role"],
                    merch_spec["display_name"],
                    merch_spec["phone"],
                ),
            )
            merch_user_id = cur.lastrowid
            summary["users_created"] += 1
        else:
            merch_user_id = u_row["id"]
            summary["users_existing"] += 1

        db.execute(
            """INSERT OR IGNORE INTO user_preferences (user_id, interests, budget_min, budget_max, preferred_brands, currency)
               VALUES (?, '[]', 0, 100000, '[]', 'INR')""",
            (merch_user_id,),
        )
        db.execute("INSERT OR IGNORE INTO notification_preferences (user_id) VALUES (?)", (merch_user_id,))
        db.execute(
            "INSERT OR IGNORE INTO consent_records (user_id, consent_type, granted) VALUES (?, 'terms_and_privacy', 1)",
            (merch_user_id,),
        )

        # Partner record
        p_info = merch_spec["partner"]
        p_row = db.execute("SELECT id FROM partners WHERE user_id = ?", (merch_user_id,)).fetchone()
        if not p_row:
            cur = db.execute(
                """INSERT INTO partners (user_id, business_name, website, business_email, partner_type, category, status)
                   VALUES (?, ?, ?, ?, 'merchant', ?, ?)""",
                (merch_user_id, p_info["business_name"], p_info["website"], p_info["business_email"], p_info["category"], p_info["status"]),
            )
            partner_id = cur.lastrowid
            summary["partners_created"] += 1
        else:
            partner_id = p_row["id"]
            summary["partners_existing"] += 1

        partner_id_map[p_info["sku_prefix"]] = partner_id

        # Sample import job for each partner
        existing_job = db.execute("SELECT id FROM feed_import_jobs WHERE partner_id = ?", (partner_id,)).fetchone()
        if not existing_job:
            db.execute(
                """INSERT INTO feed_import_jobs (partner_id, filename, status, items_total, items_imported, items_skipped)
                   VALUES (?, 'catalogue_feed_v1.csv', 'completed', 20, 20, 0)""",
                (partner_id,),
            )
            summary["import_jobs_created"] += 1

    # 3. CONSUMERS (25)
    consumer_ids = []
    for idx, (name, interests, b_min, b_max, brands) in enumerate(CONSUMER_PROFILES, start=1):
        email = f"consumer.{idx:02d}@example.com"
        u_row = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not u_row:
            cur = db.execute(
                """INSERT INTO users (email, password_hash, role, display_name, phone, is_verified, status)
                   VALUES (?, ?, 'consumer', ?, ?, 1, 'active')""",
                (
                    email,
                    generate_password_hash("ConsumerDemo2026!"),
                    name,
                    f"+91 98765 2{idx:04d}",
                ),
            )
            c_id = cur.lastrowid
            summary["users_created"] += 1
        else:
            c_id = u_row["id"]
            summary["users_existing"] += 1

        consumer_ids.append(c_id)

        # Update / insert rich preferences
        db.execute(
            """INSERT OR REPLACE INTO user_preferences (user_id, interests, budget_min, budget_max, preferred_brands, currency)
               VALUES (?, ?, ?, ?, ?, 'INR')""",
            (c_id, json.dumps(interests), b_min, b_max, json.dumps(brands)),
        )
        summary["preferences_configured"] += 1

        db.execute(
            """INSERT OR IGNORE INTO notification_preferences (user_id, email_alerts, price_drop_alerts, availability_alerts, digest_frequency)
               VALUES (?, 1, 1, 1, 'daily')""",
            (c_id,),
        )
        for ctype in ("terms_and_privacy", "personalization", "marketing_emails"):
            db.execute(
                "INSERT OR IGNORE INTO consent_records (user_id, consent_type, granted) VALUES (?, ?, 1)",
                (c_id, ctype),
            )

    # 4. PRODUCTS (100 total, 20 per partner)
    seeded_product_ids = []
    approved_product_ids = []
    for sku_prefix, items in PRODUCT_GROUPS:
        partner_id = partner_id_map.get(sku_prefix)
        for num, (title, desc, cat, brand, price, avail, mod_status) in enumerate(items, start=1):
            sku = f"DEMO-{sku_prefix}-{num:03d}"
            prod_url = f"https://example.com/demo/products/{sku.lower()}"
            img_url = f"/static/images/products/{cat}.jpg"

            p_row = db.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()
            if not p_row:
                cur = db.execute(
                    """INSERT INTO products (
                           partner_id, sku, title, description, category, brand, price,
                           currency, availability, image_url, product_url, feed_source,
                           is_sponsored, moderation_status, last_updated_at, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, 'INR', ?, ?, ?, 'demo', 0, ?, ?, ?)""",
                    (partner_id, sku, title, desc, cat, brand, price, avail, img_url, prod_url, mod_status, now_iso, now_iso),
                )
                pid = cur.lastrowid
                summary["products_created"] += 1
            else:
                pid = p_row["id"]
                summary["products_existing"] += 1

            seeded_product_ids.append(pid)
            if mod_status == "approved" and avail == "in_stock":
                approved_product_ids.append((pid, partner_id, title))

    # 5. FEEDS & ARTICLES
    feed_id_map = {}
    for f_spec in DEMO_FEEDS:
        f_row = db.execute("SELECT id FROM feeds WHERE url = ?", (f_spec["url"],)).fetchone()
        last_fetch = (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 12))).isoformat()
        if not f_row:
            cur = db.execute(
                """INSERT INTO feeds (url, title, last_fetched_at, last_fetch_status, last_error)
                   VALUES (?, ?, ?, ?, ?)""",
                (f_spec["url"], f_spec["title"], last_fetch, f_spec["status"], f_spec.get("error")),
            )
            fid = cur.lastrowid
            summary["feeds_created"] += 1
        else:
            fid = f_row["id"]
            summary["feeds_existing"] += 1

        feed_id_map[f_spec["url"]] = (fid, f_spec["category"])

    # Seed 60 articles across the feeds
    article_samples = [
        ("Next-Generation Solid-State Batteries Enter Mass Production", "A breakthrough in ceramic electrolyte stability paves the way for electric vehicles with 1,000 km range.", "technology"),
        ("The Rise of On-Device Neural Processing Units", "How local generative inference on smartphones and laptops is preserving user privacy while reducing cloud latency.", "technology"),
        ("Open-Source Foundation Models Close Gap with Proprietary Systems", "Benchmark metrics show community fine-tuned models matching top tier commercial systems on reasoning tasks.", "technology"),
        ("Quantum Computing Reaches High-Fidelity Logical Qubit Milestone", "Researchers demonstrate fault-tolerant quantum error correction suppressing decoherence rates tenfold.", "technology"),
        ("Wearable Biometric Sensors Shift from Fitness to Preventive Medicine", "Next-gen sensors continuously track interstitial glucose and arterial stiffness with clinical accuracy.", "technology"),
        ("Sustainable Tailoring: The Resurgence of Circular Apparel", "European fashion houses embrace closed-loop recycled yarns and digital product passports to reduce waste.", "fashion"),
        ("Smart Fabrics with Integrated Conductive Yarns for Thermal Regulation", "Performance wear merges microscopic phase-change materials to adapt dynamically to exterior ambient temperatures.", "fashion"),
        ("Minimalist Aesthetic Drives Demand for Timeless Wardrobe Staples", "Consumers pivot away from fast fashion in favor of durable, repairable, high-grade organic textiles.", "fashion"),
        ("Plant-Based Leather Alternatives Achieve Luxury-Grade Durability", "Mycelium and cactus-derived leather alternatives replace synthetic polyurethanes across luxury accessories.", "fashion"),
        ("3D Knitted Footwear Reduces Manufacturing Waste by 80 Percent", "Seamless automated additive knitting eliminates fabric offcuts while improving arch support customization.", "fashion"),
        ("Biophilic Interior Design: Incorporating Natural Light and Living Greenery", "Modern residential architects prioritize living green walls and circadian-attuned lighting layouts.", "home"),
        ("Passive House Standards Become Mainstream in Urban Architecture", "Triple-glazed super-insulated homes slash heating and cooling energy expenditures by over 70 percent.", "home"),
        ("Induction Cooking Replaces Gas in Modern Energy-Efficient Kitchens", "Chefs and homeowners transition to high-precision magnetic induction for superior heat efficiency and indoor air quality.", "home"),
        ("Smart Home Interoperability Accelerates Under the Matter Protocol", "Cross-ecosystem smart lighting, security, and climate sensors now connect seamlessly across all major hubs.", "home"),
        ("Compact Modular Furniture Solves Micro-Apartment Spatial Constraints", "Transformable multi-use furniture designs empower apartment dwellers with dynamic living and working layouts.", "home"),
        ("The Enduring Appeal of Deep Reading in a Hyper-Distracted World", "Cognitive psychologists explore how long-form immersive reading restores attention spans and empathy.", "learning"),
        ("Modern Software Architecture: Moving from Microservice Sprawl to Modular Monoliths", "Why engineering teams are consolidating distributed network boundaries into well-isolated domain engines.", "learning"),
        ("Financial Literacy in the Digital Era: Automated Indexing and Behavioral Guardrails", "How algorithmic low-cost systematic investment plans empower first-time investors with disciplined compounding.", "learning"),
        ("The Science of Spaced Repetition for Accelerated Technical Mastery", "Active recall and algorithmic intervals transform how software engineers retain algorithms and systems fundamentals.", "learning"),
        ("Lifelong Learning Platforms Pivot Toward Project-Based Portfolio Assessments", "Employers increasingly value verified repository contributions over traditional credential certificates.", "learning"),
        ("Zone 2 Cardiovascular Training: The Metabolic Engine of Longevity", "Cardiologists and endurance coaches highlight why low-intensity aerobic volume optimizes mitochondrial health.", "sports"),
        ("Periodized Strength Training for Joint Longevity and Bone Density", "Progressive overload protocols demonstrate superior musculoskeletal preservation across aging athletic populations.", "sports"),
        ("Cold Water Immersion vs. Active Recovery: What Current Science Shows", "New sports science trials illuminate when cryotherapy aids recovery versus when it blunts muscular hypertrophy.", "sports"),
        ("Sleep Architecture and Athletic Performance: Optimizing Deep and REM Cycles", "Wearable telemetry confirms that consistent bedtime schedules boost reaction time and reduce sports injury risks.", "sports"),
        ("Plant-Powered Athletic Nutrition: Meeting Protein Synthesis Demands", "How elite endurance and strength athletes balance leucine profiles using diversified whole-food plant proteins.", "sports"),
    ]

    feed_urls = [f["url"] for f in DEMO_FEEDS if f["status"] == "ok"]
    for i in range(60):
        sample_title, sample_summary, sample_cat = article_samples[i % len(article_samples)]
        title = f"{sample_title} (Report #{i+1:02d})"
        art_url = f"https://example.com/articles/demo-{i+1:03d}"
        feed_url = feed_urls[i % len(feed_urls)]
        fid, _ = feed_id_map[feed_url]
        pub_date = (datetime.now(timezone.utc) - timedelta(days=(i % 14), hours=(i % 24))).isoformat()

        a_row = db.execute("SELECT id FROM articles WHERE url = ?", (art_url,)).fetchone()
        if not a_row:
            db.execute(
                """INSERT INTO articles (feed_id, title, url, summary, category, published_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (fid, title, art_url, sample_summary, sample_cat, pub_date),
            )
            summary["articles_created"] += 1
        else:
            summary["articles_existing"] += 1

    # 6. CONSUMER INTERACTIONS (Saved Items & Feedback)
    if consumer_ids and seeded_product_ids:
        for idx, cid in enumerate(consumer_ids[:15]):
            # Save 2 distinct products for this consumer
            p1 = seeded_product_ids[(idx * 2) % len(seeded_product_ids)]
            p2 = seeded_product_ids[(idx * 2 + 1) % len(seeded_product_ids)]
            for pid, note in [(p1, "Saved to comparison wishlist"), (p2, "Waiting for festival discount")]:
                existing_save = db.execute("SELECT id FROM saved_items WHERE user_id = ? AND product_id = ?", (cid, pid)).fetchone()
                if not existing_save:
                    db.execute(
                        "INSERT INTO saved_items (user_id, product_id, note) VALUES (?, ?, ?)",
                        (cid, pid, note),
                    )
                    summary["saved_items_created"] += 1

        # Dismissal and like feedback
        for idx, cid in enumerate(consumer_ids[15:20]):
            dismiss_pid = seeded_product_ids[(idx * 3) % len(seeded_product_ids)]
            db.execute(
                "INSERT INTO user_feedback (user_id, product_id, action, reason) VALUES (?, ?, 'dismiss', 'too_expensive')",
                (cid, dismiss_pid),
            )
            summary["feedback_created"] += 1

        for idx, cid in enumerate(consumer_ids[20:25]):
            like_pid = seeded_product_ids[(idx * 4) % len(seeded_product_ids)]
            db.execute(
                "INSERT INTO user_feedback (user_id, product_id, action, reason) VALUES (?, ?, 'like', 'interested_in_brand')",
                (cid, like_pid),
            )
            summary["feedback_created"] += 1

    # 7. PRICE ALERTS & NOTIFICATIONS
    if consumer_ids and seeded_product_ids:
        sample_notifications = [
            ("price_drop", "Price Drop Alert", "Apex Phone 15 Pro Max dropped by ₹4,000 to ₹79,999"),
            ("recommendation", "Curated For You", "Based on your interest in Audio: NoiseCancel 750 Headphones"),
            ("availability", "Back in Stock", "Velocity Cast-Iron Kettlebell 16kg is now in stock"),
            ("feed_status", "Feed Ingestion Complete", "Tech Trends & Computing Innovations updated with new stories"),
            ("price_drop", "Price Drop Alert", "Smart HEPA Air Purifier Pro dropped by 10%"),
            ("recommendation", "New Arrival in Learning", "Designing Data-Intensive Applications available now"),
        ]
        for idx, cid in enumerate(consumer_ids):
            event_type, n_title, n_msg = sample_notifications[idx % len(sample_notifications)]
            pid = seeded_product_ids[idx % len(seeded_product_ids)]
            is_read = 1 if (idx % 2 == 0) else 0
            db.execute(
                """INSERT INTO notification_events (user_id, product_id, event_type, title, message, is_read)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (cid, pid, event_type, n_title, n_msg, is_read),
            )
            summary["notifications_created"] += 1

    # 8. AFFILIATE CLICKS & CONVERSIONS
    if consumer_ids and approved_product_ids:
        for idx in range(30):
            click_id = f"demo_click_{idx+1:03d}"
            pid, partner_id, ptitle = approved_product_ids[idx % len(approved_product_ids)]
            cid = consumer_ids[idx % len(consumer_ids)]
            tracking_url = f"https://example.com/affiliate/track?click_id={click_id}&pid={pid}"

            existing_click = db.execute("SELECT id FROM affiliate_clicks WHERE click_id = ?", (click_id,)).fetchone()
            if not existing_click:
                is_converted = 1 if (idx % 4 == 0) else 0
                conv_amt = round(random.uniform(1500.0, 45000.0), 2) if is_converted else 0.0
                comm_amt = round(conv_amt * 0.05, 2) if is_converted else 0.0
                order_id = f"DEMO-ORD-{9000 + idx}" if is_converted else None
                conv_at = (datetime.now(timezone.utc) - timedelta(days=idx % 7)).isoformat() if is_converted else None

                db.execute(
                    """INSERT INTO affiliate_clicks (
                           user_id, product_id, partner_id, click_id, tracking_url,
                           converted, conversion_amount, commission_amount, order_id, converted_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (cid, pid, partner_id, click_id, tracking_url, is_converted, conv_amt, comm_amt, order_id, conv_at),
                )
                summary["affiliate_clicks_created"] += 1

    # 9. MERCHANT CAMPAIGNS (9 realistic sample campaigns)
    if approved_product_ids:
        today_date = datetime.now(timezone.utc).date()
        campaign_specs = [
            ("Apex Phone 15 Flagship Campaign", 0, "active", today_date - timedelta(days=5), today_date + timedelta(days=25), 1500.0, 45000.0, None),
            ("NoiseCancel 750 Audio Spotlight", 4, "active", today_date - timedelta(days=2), today_date + timedelta(days=18), 800.0, 20000.0, None),
            ("Oxford Shirt Smart Casual Promo", 1, "active", today_date - timedelta(days=7), today_date + timedelta(days=21), 600.0, 15000.0, None),
            ("Air Purifier Clean Living Drive", 2, "active", today_date - timedelta(days=3), today_date + timedelta(days=30), 1000.0, 30000.0, None),
            ("Data Systems Handbook Launch", 3, "pending", today_date, today_date + timedelta(days=30), 500.0, 15000.0, None),
            ("Kettlebell Strength Equipment Feature", 4, "pending", today_date, today_date + timedelta(days=14), 750.0, 12000.0, None),
            ("Ultraboost Spring Clearance", 1, "completed", today_date - timedelta(days=45), today_date - timedelta(days=5), 1200.0, 48000.0, None),
            ("Apex Audio Budget Blast", 0, "rejected", today_date - timedelta(days=10), today_date + timedelta(days=10), 1000.0, 20000.0, "Missing required brand authorization disclosure"),
            ("Speed Jump Rope Flash Sponsorship", 4, "suspended", today_date - timedelta(days=15), today_date + timedelta(days=15), 400.0, 10000.0, "Temporarily paused pending inventory replenishment"),
        ]

        for title, p_idx, status, start_d, end_d, d_budget, t_budget, rej_reason in campaign_specs:
            pid, partner_id, ptitle = approved_product_ids[p_idx % len(approved_product_ids)]
            c_row = db.execute(
                "SELECT id FROM campaigns WHERE partner_id = ? AND title = ?",
                (partner_id, title),
            ).fetchone()
            if not c_row:
                db.execute(
                    """INSERT INTO campaigns (
                           partner_id, product_id, title, daily_budget, total_budget,
                           start_date, end_date, max_impressions_per_user, status, rejection_reason
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, 3, ?, ?)""",
                    (partner_id, pid, title, d_budget, t_budget, start_d.isoformat(), end_d.isoformat(), status, rej_reason),
                )
                summary["campaigns_created"] += 1
            else:
                summary["campaigns_existing"] += 1

    # 10. ADMIN AUDIT LOGS
    admin_actions = [
        ("partner_status_change", "partner", 1, "Approved partner application for Apex Electronics"),
        ("partner_status_change", "partner", 2, "Approved partner application for Luxe Trendwear"),
        ("partner_status_change", "partner", 3, "Approved partner application for Urban Nest Living"),
        ("campaign_status_change", "campaign", 1, "Approved campaign 'Apex Phone 15 Flagship Campaign'"),
        ("campaign_status_change", "campaign", 8, "Rejected campaign 'Apex Audio Budget Blast'. Reason: Missing authorization disclosure"),
        ("product_moderation", "product", 20, "Rejected uncertified laser projector due to regulatory compliance"),
    ]
    for action, target_type, target_id, details in admin_actions:
        db.execute(
            """INSERT INTO audit_logs (user_id, action, target_type, target_id, details, ip_address)
               VALUES (?, ?, ?, ?, ?, '127.0.0.1')""",
            (admin_id, action, target_type, target_id, details),
        )
        summary["audit_logs_created"] += 1

    db.commit()
    return summary


def reset_all_demo_data(db) -> dict:
    """Safely delete only demo records, strictly preserving user-created accounts and data."""
    summary = {
        "users_deleted": 0,
        "partners_deleted": 0,
        "products_deleted": 0,
        "feeds_deleted": 0,
        "articles_deleted": 0,
        "campaigns_deleted": 0,
        "affiliate_clicks_deleted": 0,
        "saved_items_deleted": 0,
        "feedback_deleted": 0,
        "notifications_deleted": 0,
        "import_jobs_deleted": 0,
        "audit_logs_deleted": 0,
    }

    # Find demo users (example.com accounts created for demo)
    demo_users = db.execute(
        """SELECT id FROM users
           WHERE email LIKE '%@example.com'
             AND (email = 'admin@example.com' OR email LIKE 'merchant.%@example.com' OR email LIKE 'consumer.%@example.com')"""
    ).fetchall()
    demo_user_ids = [r["id"] for r in demo_users]

    # Find demo partners
    demo_partners = db.execute(
        "SELECT id FROM partners WHERE website LIKE '%example.com%' OR business_email LIKE '%example.com%'"
    ).fetchall()
    demo_partner_ids = [r["id"] for r in demo_partners]

    # Delete demo campaigns
    if demo_partner_ids:
        placeholders = ",".join("?" for _ in demo_partner_ids)
        c_count = db.execute(f"DELETE FROM campaigns WHERE partner_id IN ({placeholders})", tuple(demo_partner_ids)).rowcount
        summary["campaigns_deleted"] = c_count

        # Delete demo import jobs
        j_count = db.execute(f"DELETE FROM feed_import_jobs WHERE partner_id IN ({placeholders})", tuple(demo_partner_ids)).rowcount
        summary["import_jobs_deleted"] = j_count

    # Delete demo affiliate clicks
    summary["affiliate_clicks_deleted"] = db.execute("DELETE FROM affiliate_clicks WHERE click_id LIKE 'demo_click_%'").rowcount

    # Delete demo feedback and saved items for demo users
    if demo_user_ids:
        u_placeholders = ",".join("?" for _ in demo_user_ids)
        summary["saved_items_deleted"] = db.execute(f"DELETE FROM saved_items WHERE user_id IN ({u_placeholders})", tuple(demo_user_ids)).rowcount
        summary["feedback_deleted"] = db.execute(f"DELETE FROM user_feedback WHERE user_id IN ({u_placeholders})", tuple(demo_user_ids)).rowcount
        summary["notifications_deleted"] = db.execute(f"DELETE FROM notification_events WHERE user_id IN ({u_placeholders})", tuple(demo_user_ids)).rowcount

    # Delete demo products (feed_source = 'demo' or sku LIKE 'DEMO-%')
    p_count = db.execute("DELETE FROM products WHERE feed_source = 'demo' OR sku LIKE 'DEMO-%'").rowcount
    summary["products_deleted"] = p_count

    # Delete demo feeds & articles
    demo_feeds = db.execute("SELECT id FROM feeds WHERE url LIKE 'https://example.com/demo-feeds/%'").fetchall()
    demo_feed_ids = [r["id"] for r in demo_feeds]
    if demo_feed_ids:
        f_placeholders = ",".join("?" for _ in demo_feed_ids)
        summary["articles_deleted"] = db.execute(f"DELETE FROM articles WHERE feed_id IN ({f_placeholders})", tuple(demo_feed_ids)).rowcount
        summary["feeds_deleted"] = db.execute(f"DELETE FROM feeds WHERE id IN ({f_placeholders})", tuple(demo_feed_ids)).rowcount

    # Delete demo partners
    if demo_partner_ids:
        p_placeholders = ",".join("?" for _ in demo_partner_ids)
        summary["partners_deleted"] = db.execute(f"DELETE FROM partners WHERE id IN ({p_placeholders})", tuple(demo_partner_ids)).rowcount

    # Delete demo users (preferences, consent, notifications cascade or delete)
    if demo_user_ids:
        u_placeholders = ",".join("?" for _ in demo_user_ids)
        db.execute(f"DELETE FROM user_preferences WHERE user_id IN ({u_placeholders})", tuple(demo_user_ids))
        db.execute(f"DELETE FROM consent_records WHERE user_id IN ({u_placeholders})", tuple(demo_user_ids))
        db.execute(f"DELETE FROM notification_preferences WHERE user_id IN ({u_placeholders})", tuple(demo_user_ids))
        summary["users_deleted"] = db.execute(f"DELETE FROM users WHERE id IN ({u_placeholders})", tuple(demo_user_ids)).rowcount

    # Delete demo audit logs
    summary["audit_logs_deleted"] = db.execute("DELETE FROM audit_logs WHERE details LIKE '%Apex Electronics%' OR details LIKE '%Luxe Trendwear%' OR details LIKE '%Urban Nest%'").rowcount

    db.commit()
    return summary
