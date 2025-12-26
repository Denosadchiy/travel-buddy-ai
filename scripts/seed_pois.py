"""
Script to seed the database with example POIs for testing.
Run with: python -m scripts.seed_pois
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.database import AsyncSessionLocal
from src.infrastructure.models import POIModel


# Example POIs for different cities
SAMPLE_POIS = [
    # Paris POIs
    {
        "name": "Eiffel Tower",
        "city": "Paris",
        "category": "attraction",
        "tags": ["landmark", "culture", "views", "iconic"],
        "rating": 4.7,
        "location": "Champ de Mars, 5 Avenue Anatole France, 75007 Paris",
        "opening_hours": {"mon-sun": "09:30-23:45"},
        "description": "Iconic iron lattice tower and symbol of Paris"
    },
    {
        "name": "Louvre Museum",
        "city": "Paris",
        "category": "museum",
        "tags": ["culture", "art", "museum", "history"],
        "rating": 4.8,
        "location": "Rue de Rivoli, 75001 Paris",
        "opening_hours": {"mon": "closed", "tue-sun": "09:00-18:00"},
        "description": "World's largest art museum and historic monument"
    },
    {
        "name": "Le Comptoir du Relais",
        "city": "Paris",
        "category": "restaurant",
        "tags": ["food", "french cuisine", "bistro"],
        "rating": 4.5,
        "location": "9 Carrefour de l'Odéon, 75006 Paris",
        "opening_hours": {"mon-sun": "12:00-23:00"},
        "description": "Classic French bistro in Saint-Germain"
    },
    {
        "name": "Sacré-Cœur Basilica",
        "city": "Paris",
        "category": "attraction",
        "tags": ["culture", "architecture", "views", "religious"],
        "rating": 4.7,
        "location": "35 Rue du Chevalier de la Barre, 75018 Paris",
        "opening_hours": {"mon-sun": "06:00-22:30"},
        "description": "Beautiful basilica atop Montmartre hill"
    },
    {
        "name": "Rex Club",
        "city": "Paris",
        "category": "nightlife",
        "tags": ["nightlife", "techno", "club", "electronic music"],
        "rating": 4.4,
        "location": "5 Boulevard Poissonnière, 75002 Paris",
        "opening_hours": {"wed-sat": "23:30-06:00"},
        "description": "Legendary techno club with world-class sound system"
    },

    # Tokyo POIs
    {
        "name": "Senso-ji Temple",
        "city": "Tokyo",
        "category": "attraction",
        "tags": ["culture", "religious", "history", "traditional"],
        "rating": 4.6,
        "location": "2-3-1 Asakusa, Taito City, Tokyo",
        "opening_hours": {"mon-sun": "06:00-17:00"},
        "description": "Ancient Buddhist temple in Asakusa"
    },
    {
        "name": "Sushi Dai",
        "city": "Tokyo",
        "category": "restaurant",
        "tags": ["food", "sushi", "seafood", "japanese cuisine"],
        "rating": 4.7,
        "location": "Toyosu Market, 6-6-2 Toyosu, Koto City, Tokyo",
        "opening_hours": {"mon-sat": "05:00-13:00", "sun": "closed"},
        "description": "Famous sushi restaurant at Toyosu Market"
    },
    {
        "name": "TeamLab Borderless",
        "city": "Tokyo",
        "category": "museum",
        "tags": ["art", "digital", "interactive", "modern"],
        "rating": 4.8,
        "location": "1-3-8 Aomi, Koto City, Tokyo",
        "opening_hours": {"mon-sun": "10:00-19:00"},
        "description": "Immersive digital art museum"
    },
    {
        "name": "Shibuya Sky",
        "city": "Tokyo",
        "category": "attraction",
        "tags": ["views", "modern", "observation deck"],
        "rating": 4.6,
        "location": "2-24-12 Shibuya, Shibuya City, Tokyo",
        "opening_hours": {"mon-sun": "10:00-22:30"},
        "description": "Rooftop observation deck with panoramic city views"
    },
    {
        "name": "Womb",
        "city": "Tokyo",
        "category": "nightlife",
        "tags": ["nightlife", "club", "electronic music", "techno"],
        "rating": 4.5,
        "location": "2-16 Maruyamacho, Shibuya City, Tokyo",
        "opening_hours": {"fri-sat": "23:00-05:00"},
        "description": "Premier electronic music club in Shibuya"
    },

    # Barcelona POIs
    {
        "name": "Sagrada Familia",
        "city": "Barcelona",
        "category": "attraction",
        "tags": ["architecture", "culture", "religious", "gaudi"],
        "rating": 4.8,
        "location": "Carrer de Mallorca, 401, 08013 Barcelona",
        "opening_hours": {"mon-sun": "09:00-20:00"},
        "description": "Iconic unfinished basilica by Antoni Gaudí"
    },
    {
        "name": "La Boqueria Market",
        "city": "Barcelona",
        "category": "food_market",
        "tags": ["food", "market", "local", "tapas"],
        "rating": 4.5,
        "location": "La Rambla, 91, 08001 Barcelona",
        "opening_hours": {"mon-sat": "08:00-20:30", "sun": "closed"},
        "description": "Famous food market on La Rambla"
    },
    {
        "name": "Park Güell",
        "city": "Barcelona",
        "category": "attraction",
        "tags": ["park", "architecture", "gaudi", "views"],
        "rating": 4.6,
        "location": "08024 Barcelona",
        "opening_hours": {"mon-sun": "08:00-21:30"},
        "description": "Colorful park designed by Antoni Gaudí"
    },
    {
        "name": "Cervecería Catalana",
        "city": "Barcelona",
        "category": "restaurant",
        "tags": ["food", "tapas", "spanish cuisine", "local"],
        "rating": 4.4,
        "location": "Carrer de Mallorca, 236, 08008 Barcelona",
        "opening_hours": {"mon-sun": "08:00-01:30"},
        "description": "Popular tapas bar in Eixample"
    },
    {
        "name": "Razzmatazz",
        "city": "Barcelona",
        "category": "nightlife",
        "tags": ["nightlife", "club", "live music", "electronic music"],
        "rating": 4.3,
        "location": "Carrer dels Almogàvers, 122, 08018 Barcelona",
        "opening_hours": {"fri-sat": "00:00-06:00"},
        "description": "Multi-room nightclub with diverse music"
    },
]


async def seed_database():
    """Seed the database with sample POIs."""
    async with AsyncSessionLocal() as session:
        try:
            print("Starting POI seeding...")

            # Check if POIs already exist
            from sqlalchemy import select
            result = await session.execute(select(POIModel))
            existing_pois = result.scalars().all()

            if existing_pois:
                print(f"Database already contains {len(existing_pois)} POIs.")
                response = input("Do you want to clear and reseed? (y/n): ")
                if response.lower() == 'y':
                    for poi in existing_pois:
                        await session.delete(poi)
                    await session.commit()
                    print("Cleared existing POIs.")
                else:
                    print("Seeding cancelled.")
                    return

            # Add sample POIs
            for poi_data in SAMPLE_POIS:
                poi = POIModel(**poi_data)
                session.add(poi)

            await session.commit()
            print(f"Successfully seeded {len(SAMPLE_POIS)} POIs!")

            # Display summary
            cities = {}
            for poi in SAMPLE_POIS:
                city = poi["city"]
                cities[city] = cities.get(city, 0) + 1

            print("\nPOIs by city:")
            for city, count in cities.items():
                print(f"  {city}: {count} POIs")

        except Exception as e:
            print(f"Error seeding database: {e}")
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(seed_database())
