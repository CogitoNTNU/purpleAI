import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from businesses.models import Business, BusinessClaim
from reviews.models import Review, Vote
import shutil
import os
from django.conf import settings

User = get_user_model()


class Command(BaseCommand):
    help = "Populate the database with dummy data"

    def handle(self, *args, **kwargs):
        self.stdout.write("Clearing media folder...")
        if os.path.exists(settings.MEDIA_ROOT):
            shutil.rmtree(settings.MEDIA_ROOT)

        os.makedirs(settings.MEDIA_ROOT)

        self.stdout.write("Clearing existing data...")
        Vote.objects.all().delete()
        Review.objects.all().delete()
        BusinessClaim.objects.all().delete()
        Business.objects.all().delete()
        User.objects.all().delete()

        self.stdout.write("Populating database...")

        # Create Users
        admins = []
        owners = []
        reviewers = []

        # Admin
        ssn = "".join([str(random.randint(0, 9)) for _ in range(11)])
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "first_name": "Admin",
                "last_name": "User",
                "role": "admin",
                "ssn": ssn,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin.set_password("admin")
            admin.save()
            self.stdout.write(f"Created admin user: {admin.username}")
        admins.append(admin)

        # Business Owners
        for i in range(1, 4):
            username = f"owner{i}"
            ssn = "".join([str(random.randint(0, 9)) for _ in range(11)])
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                    "first_name": "Business",
                    "last_name": f"Owner {i}",
                    "role": "business_owner",
                    "ssn": ssn,
                },
            )
            if created:
                user.set_password("password")
                user.save()
                self.stdout.write(f"Created owner: {user.username}")
            owners.append(user)

        # Reviewers
        for i in range(1, 6):
            username = f"reviewer{i}"
            ssn = "".join([str(random.randint(0, 9)) for _ in range(11)])
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                    "first_name": "Reviewer",
                    "last_name": f"User {i}",
                    "role": "reviewer",
                    "ssn": ssn,
                },
            )
            if created:
                user.set_password("password")
                user.save()
                self.stdout.write(f"Created reviewer: {user.username}")
            reviewers.append(user)

        # Create Businesses
        CATEGORY_DATA = {
            Business.Category.RESTAURANTS_AND_BARS: [
                "The Rusty Spoon",
                "Secure Eats",
                "Buggy Bistro",
                "Pixel Bar",
                "Code Cafe",
                "Taste of Italy",
                "Burger King",
            ],
            Business.Category.ENTERTAINMENT: [
                "Night Owl Club",
                "Retro Arcade",
                "Vinyl Heaven",
                "Cinema Paradiso",
                "The Laugh Factory",
                "Bowling Alley",
            ],
            Business.Category.FASHION: [
                "Fashion Forward",
                "Vintage Vogue",
                "Chic Boutique",
                "Denim Den",
                "Silk & Satin",
                "Trendy Threads",
            ],
            Business.Category.ELECTRONIC: [
                "Tech Trends",
                "Gadget Grove",
                "Circuit City",
                "Digital Dreams",
                "The Computer Store",
                "Electro World",
            ],
        }

        businesses = []
        for category, names in CATEGORY_DATA.items():
            for name in names:
                owner = random.choice(owners)
                business, created = Business.objects.get_or_create(
                    name=name,
                    defaults={
                        "owner": owner,
                        "description": f"This is a great place for {category}. Come visit {name}!",
                        "category": category,
                        "address": f"Prinsens gate {random.randint(1, 100)}, Trondheim",
                        "verified": random.choice([True, False]),
                    },
                )
                if created:
                    self.stdout.write(f"Created business: {business.name} ({category})")
                businesses.append(business)

        # Create Reviews
        REVIEW_TEMPLATES = {
            Business.Category.RESTAURANTS_AND_BARS: [
                {
                    "title": "Delicious food",
                    "body": "The food at {business_name} was amazing! Highly recommend the steak.",
                    "rating_min": 4,
                    "rating_max": 5,
                },
                {
                    "title": "Terrible service",
                    "body": "Waiter was rude at {business_name}. Food was cold.",
                    "rating_min": 1,
                    "rating_max": 2,
                },
                {
                    "title": "Great drinks",
                    "body": "Love the cocktail selection at {business_name}.",
                    "rating_min": 4,
                    "rating_max": 5,
                },
                {
                    "title": "Average meal",
                    "body": "Food was okay, but a bit salty. Service was fine.",
                    "rating_min": 3,
                    "rating_max": 3,
                },
            ],
            Business.Category.ENTERTAINMENT: [
                {
                    "title": "So much fun!",
                    "body": "Had a blast at {business_name}. Great music and vibe.",
                    "rating_min": 5,
                    "rating_max": 5,
                },
                {
                    "title": "Boring",
                    "body": "{business_name} was not as fun as I expected. Crowd was dead.",
                    "rating_min": 2,
                    "rating_max": 3,
                },
                {
                    "title": "Good for weekends",
                    "body": "Nice place to hang out on a Saturday night.",
                    "rating_min": 4,
                    "rating_max": 4,
                },
            ],
            Business.Category.FASHION: [
                {
                    "title": "Great quality",
                    "body": "Bought a dress at {business_name} and the fabric is lovely.",
                    "rating_min": 4,
                    "rating_max": 5,
                },
                {
                    "title": "Overpriced",
                    "body": "{business_name} is way too expensive for what you get.",
                    "rating_min": 2,
                    "rating_max": 3,
                },
                {
                    "title": "Awesome collection",
                    "body": "They have the latest trends here. Love it!",
                    "rating_min": 5,
                    "rating_max": 5,
                },
            ],
            Business.Category.ELECTRONIC: [
                {
                    "title": "Latest gadgets",
                    "body": "{business_name} has all the newest tech. Staff knows their stuff.",
                    "rating_min": 5,
                    "rating_max": 5,
                },
                {
                    "title": "Broken item",
                    "body": "Bought a laptop from {business_name} and it broke in week. Support was unhelpful.",
                    "rating_min": 1,
                    "rating_max": 1,
                },
                {
                    "title": "Decent prices",
                    "body": "Good selection of cables and chargers.",
                    "rating_min": 4,
                    "rating_max": 4,
                },
            ],
        }

        # Ensure we have at least one review per business, plus random extras
        for business in businesses:
            # Add 1-3 reviews per business
            for _ in range(random.randint(1, 3)):
                reviewer = random.choice(reviewers)

                templates = REVIEW_TEMPLATES.get(business.category, [])
                if not templates:
                    continue

                template = random.choice(templates)
                rating = random.randint(template["rating_min"], template["rating_max"])

                Review.objects.create(
                    author=reviewer,
                    business=business,
                    title=template["title"],
                    body=template["body"].format(business_name=business.name),
                    rating=rating,
                )
                self.stdout.write(
                    f"Created review by {reviewer.username} for {business.name}"
                )

        # Create Claims (Pending)
        unverified_businesses = [b for b in businesses if not b.verified]
        if unverified_businesses:
            business = unverified_businesses[0]
            owner = business.owner
            if owner:
                BusinessClaim.objects.get_or_create(
                    business=business,
                    claimant=owner,
                    statement="I own this business, please verify.",
                    status="pending",
                )
                self.stdout.write(f"Created pending claim for {business.name}")

        # Create Votes
        all_users = admins + owners + reviewers
        reviews = Review.objects.all()
        for review in reviews:
            num_votes = random.randint(0, 2)
            if not all_users:
                continue
            voters = random.sample(all_users, min(num_votes, len(all_users)))
            for voter in voters:
                Vote.objects.get_or_create(owner=voter, review=review, is_helpful=True)
            if voters:
                self.stdout.write(f"Added {len(voters)} votes to review {review.id}")

        self.stdout.write(self.style.SUCCESS("Successfully populated database"))
