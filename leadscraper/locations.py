"""Priority-ordered locations: India first (state by state), then the world.

The crawler walks these in order and keeps a cursor, so over a 24/7 run it
covers India fully first (Telangana/AP -> Karnataka/Kerala/TN -> the rest),
then major foreign countries. Edit/extend freely — order = priority.
"""

from __future__ import annotations

# India states in the priority order the user asked for, each with major cities.
INDIA: list[tuple[str, list[str]]] = [
    ("Telangana",       ["Hyderabad", "Secunderabad", "Warangal", "Karimnagar"]),
    ("Andhra Pradesh",  ["Visakhapatnam", "Vijayawada", "Guntur", "Tirupati",
                         "Nellore", "Kakinada", "Rajahmundry"]),
    ("Karnataka",       ["Bengaluru", "Mysuru", "Mangaluru", "Hubli", "Belgaum"]),
    ("Kerala",          ["Kochi", "Thiruvananthapuram", "Kozhikode", "Thrissur"]),
    ("Tamil Nadu",      ["Chennai", "Coimbatore", "Madurai", "Tiruchirappalli",
                         "Salem"]),
    ("Maharashtra",     ["Mumbai", "Pune", "Nagpur", "Nashik", "Navi Mumbai"]),
    ("Delhi NCR",       ["New Delhi", "Delhi", "Gurugram", "Gurgaon", "Noida",
                         "Ghaziabad", "Faridabad"]),
    ("Uttar Pradesh",   ["Lucknow", "Kanpur", "Varanasi", "Prayagraj"]),
    ("West Bengal",     ["Kolkata", "Howrah", "Durgapur"]),
    ("Gujarat",         ["Ahmedabad", "Gandhinagar", "Surat", "Vadodara", "Rajkot"]),
    ("Telangana/AP-2",  ["Anantapur", "Kurnool", "Khammam"]),
    ("Rajasthan",       ["Jaipur", "Udaipur", "Jodhpur"]),
    ("Madhya Pradesh",  ["Indore", "Bhopal", "Gwalior", "Jabalpur"]),
    ("Punjab/Chd",      ["Chandigarh", "Mohali", "Ludhiana", "Amritsar"]),
    ("Odisha",          ["Bhubaneswar", "Cuttack"]),
    ("Bihar/Jharkhand", ["Patna", "Ranchi", "Jamshedpur"]),
    ("Assam/NE",        ["Guwahati", "Shillong"]),
    ("Others",          ["Dehradun", "Raipur", "Nagpur", "Goa", "Coimbatore"]),
]

# Foreign countries in priority order, each with major hiring-hub cities.
WORLD: list[tuple[str, list[str]]] = [
    ("USA",         ["San Francisco", "New York", "Seattle", "Austin",
                     "Boston", "Los Angeles", "Chicago", "Dallas", "Atlanta"]),
    ("UK",          ["London", "Manchester", "Birmingham", "Edinburgh", "Leeds"]),
    ("Australia",   ["Sydney", "Melbourne", "Brisbane", "Perth"]),
    ("Canada",      ["Toronto", "Vancouver", "Montreal", "Calgary"]),
    ("UAE",         ["Dubai", "Abu Dhabi", "Sharjah"]),
    ("Singapore",   ["Singapore"]),
    ("Germany",     ["Berlin", "Munich", "Frankfurt", "Hamburg"]),
    ("Netherlands", ["Amsterdam", "Rotterdam"]),
    ("Ireland",     ["Dublin", "Cork"]),
    ("France",      ["Paris", "Lyon"]),
    ("Saudi Arabia",["Riyadh", "Jeddah"]),
    ("Qatar",       ["Doha"]),
    ("Malaysia",    ["Kuala Lumpur"]),
    ("New Zealand", ["Auckland", "Wellington"]),
]


def priority_locations() -> list[tuple[str, str]]:
    """Return [(city, 'City, Country')] in priority order: India first."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _state, cities in INDIA:
        for city in cities:
            key = city.lower()
            if key not in seen:
                seen.add(key)
                out.append((city, f"{city}, India"))
    for country, cities in WORLD:
        for city in cities:
            key = f"{city.lower()}|{country.lower()}"
            if key not in seen:
                seen.add(key)
                out.append((city, f"{city}, {country}"))
    return out
