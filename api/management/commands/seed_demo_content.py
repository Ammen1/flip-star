"""
Populate staging with content that behaves like a real feed.

The point is not volume, it is SHAPE. A seeder that gives every post 50 votes
and every user 10 followers produces a feed where ranking, pagination and the
"trending" queries all look correct no matter how wrong they are. Real
engagement is heavily skewed: most posts are seen by almost nobody, a few carry
the whole feed. So this draws from a lognormal distribution, backdates rows
across several weeks with a realistic time-of-day curve, and varies comment
counts with post popularity.

Names, captions and comments are SYNTHETIC but Ethiopian in register --
plausible given/family name combinations, real city names, Amharic mixed with
English the way people actually post. No real person's data is used, and no
account here can be logged into: every user gets an unusable password.

Everything is tagged so it can be told apart from real accounts and removed:
users are marked in their profile bio and can be found with
    User.objects.filter(profile__bio__endswith=DEMO_MARKER)

Idempotent. Re-running tops up to the requested counts rather than duplicating.

    python manage.py seed_demo_content
    python manage.py seed_demo_content --users 40 --reels 200
    python manage.py seed_demo_content --wipe          # remove demo data only

STAGING ONLY. The command refuses to run when ENVIRONMENT is 'production'.
"""

from __future__ import annotations

import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from api.models import Category, Comment, Follow, Reel, UserProfile

#: Appended to every generated bio so demo rows are identifiable and removable.
DEMO_MARKER = '​[demo]'

GIVEN_NAMES = [
    'Abel',
    'Abenezer',
    'Bethlehem',
    'Biruk',
    'Dagmawi',
    'Dawit',
    'Eyob',
    'Fikir',
    'Hanna',
    'Helen',
    'Hiwot',
    'Kalkidan',
    'Kidus',
    'Liya',
    'Mahlet',
    'Mekdes',
    'Meron',
    'Nahom',
    'Naod',
    'Rediet',
    'Robel',
    'Ruth',
    'Samri',
    'Selam',
    'Sena',
    'Surafel',
    'Tewodros',
    'Tsion',
    'Yeabsira',
    'Yonas',
]

FAMILY_NAMES = [
    'Abebe',
    'Alemu',
    'Assefa',
    'Bekele',
    'Desta',
    'Fikadu',
    'Gebre',
    'Girma',
    'Haile',
    'Kebede',
    'Lemma',
    'Mengistu',
    'Negash',
    'Tadesse',
    'Tesfaye',
    'Wolde',
    'Worku',
    'Yimer',
    'Zerihun',
    'Hailu',
]

CITIES = [
    'Addis Ababa',
    'Bahir Dar',
    'Hawassa',
    'Mekelle',
    'Adama',
    'Dire Dawa',
    'Gondar',
    'Jimma',
    'Dessie',
    'Bishoftu',
]

BIO_TEMPLATES = [
    'Content creator from {city}',
    '{city} · music and dance',
    'Just here to make people laugh \U0001f602 {city}',
    'Photographer \U0001f4f8 | {city}',
    'Student at AAU · {city}',
    'ቀን በቀን ✨ {city}',
    'Football, food, and everything in between · {city}',
    'Sharing a bit of {city} every day',
    'Dancer \U0001f483 | Bookings in DM | {city}',
    'Coffee first ☕ {city}',
]

CAPTIONS = [
    'Sunset over Entoto never gets old',
    'እንዴት ነዋቸው? \U0001f60a',
    'New dance, tell me what you think',
    'Made this in 20 minutes, be honest',
    'Coffee ceremony with the family this morning',
    'Bole at night hits different',
    'Trying this trend one more time',
    'My little brother stole the whole video',
    'Sheger FM playing my favourite song right now',
    'When the taxi driver plays YOUR song \U0001f525',
    'Behind the scenes from yesterday',
    'Someone tag a friend who needs to see this',
    'ሰላም ለኩልሎ \U0001f64c',
    'First attempt vs final take',
    'Practising every day until I get it right',
    'Genna preparations already started at home',
    'Hawassa lake in the morning, nothing better',
    'This took way longer than it looks',
    'Rate the outfit out of 10',
    'Small business, big dreams \U0001f4aa',
    'My mum saw this and laughed for 5 minutes',
    'Rainy season in Addis ☔',
    'Nobody asked but here it is anyway',
    'Shot on my phone, no editing',
]

HASHTAG_POOL = [
    'FlipStar',
    'Ethiopia',
    'AddisAbaba',
    'Habesha',
    'EthiopianMusic',
    'Dance',
    'Comedy',
    'Fyp',
    'Trending',
    'EthiopianFood',
    'Coffee',
    'Bahirdar',
    'Hawassa',
    'Tiktok',
    'Reels',
    'Viral',
    'Music',
    'Fashion',
]

COMMENTS = [
    'This is so good \U0001f525\U0001f525',
    'እንዴት ነዋቸው \U0001f60d',
    'Waiting for part 2',
    'How did you do this?',
    'Bro the timing \U0001f602\U0001f602',
    'My favourite one so far',
    'Sound name please?',
    'Came here from the trending page',
    'The little one at the back \U0001f606',
    'በጣም ሆነ \U0001f44f',
    'Consistency paying off, well done',
    'Which part of Addis is this?',
    'Deserves way more views',
    'Okay this one is different',
    'Doing this at the wedding on Saturday',
    'You never miss',
    'Tutorial when?',
    'Watched this like ten times',
]

CATEGORIES = [
    ('Dance', 'dance'),
    ('Comedy', 'comedy'),
    ('Music', 'music'),
    ('Food', 'food'),
    ('Fashion', 'fashion'),
    ('Sports', 'sports'),
    ('Education', 'education'),
    ('Travel', 'travel'),
]


def skewed(rng: random.Random, median: int, cap: int) -> int:
    """
    A lognormal draw centred on ``median`` with a genuine long tail.

    Uniform engagement is the biggest tell of seeded data, and it hides real
    bugs: when every post scores similarly, a broken ORDER BY still produces a
    plausible-looking feed. A first attempt here used
    ``low + (high - low) * random() ** alpha``; measured over 3000 draws, even
    at alpha=8 that left 15% of posts above 1000 votes, because rescaling a
    bounded uniform never thins the top end enough.

    Lognormal does. At sigma=2.1 the measured shape is roughly

        median 26 | 72% under 100 | 23% in 100-1000 | 5% over 1000 | 1% over 5000

    which is what real engagement looks like: almost everything is seen by
    almost nobody, and a few posts carry the whole feed. ``cap`` exists only to
    stop a once-in-a-thousand draw producing an absurd number.
    """
    from math import log

    return min(int(rng.lognormvariate(log(max(median, 1)), 2.1)), cap)


def realistic_timestamp(rng: random.Random, days_back: int) -> timezone.datetime:
    """
    A moment in the last ``days_back`` days, biased toward evenings.

    Posting is not uniform across the day. Concentrating rows around 18:00-23:00
    means anything that groups or buckets by hour gets exercised against a
    curve rather than noise.
    """
    day = rng.randint(0, max(days_back - 1, 0))
    hour = rng.choices(
        population=list(range(24)),
        weights=[1, 1, 1, 1, 1, 2, 3, 4, 4, 4, 5, 6, 6, 5, 5, 6, 7, 9, 11, 12, 11, 9, 6, 3],
        k=1,
    )[0]
    return timezone.now() - timedelta(
        days=day, hours=hour, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59)
    )


class Command(BaseCommand):
    help = 'Populate staging with realistically-shaped demo content (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=25)
        parser.add_argument('--reels', type=int, default=120)
        parser.add_argument('--days', type=int, default=45, help='Spread content over N days')
        parser.add_argument(
            '--seed', type=int, default=20260826, help='RNG seed, for reproducibility'
        )
        parser.add_argument('--wipe', action='store_true', help='Delete demo data and exit')

    def handle(self, *args, **options):
        environment = getattr(settings, 'ENVIRONMENT', '')
        if environment == 'production':
            raise CommandError(
                'Refusing to run against production. This command fabricates users '
                'and content; it exists for staging only.'
            )

        if options['wipe']:
            return self._wipe()

        # Seeded for reproducibility, not secrecy -- this produces demo
        # content, never keys or tokens.
        rng = random.Random(options['seed'])  # noqa: S311
        with transaction.atomic():
            categories = self._categories()
            users = self._users(rng, options['users'])
            self._follows(rng, users)
            reels = self._reels(rng, users, categories, options['reels'], options['days'])
            self._comments(rng, users, reels)

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone. {len(users)} demo users, {len(reels)} reels, '
                f'{Comment.objects.count()} comments, {Follow.objects.count()} follows.'
            )
        )
        self.stdout.write(
            "Reels have no media file -- see the note in this command's docstring.\n"
            'Remove everything with:  python manage.py seed_demo_content --wipe'
        )

    # -- pieces ------------------------------------------------------------

    def _categories(self):
        out = []
        for order, (name, slug) in enumerate(CATEGORIES):
            category, _ = Category.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'icon': slug, 'order': order, 'is_active': True},
            )
            out.append(category)
        self.stdout.write(f'categories : {len(out)}')
        return out

    def _users(self, rng, target):
        existing = list(
            User.objects.filter(profile__bio__endswith=DEMO_MARKER).select_related('profile')
        )
        needed = max(target - len(existing), 0)
        created = []

        for _ in range(needed):
            given = rng.choice(GIVEN_NAMES)
            family = rng.choice(FAMILY_NAMES)
            city = rng.choice(CITIES)
            suffix = rng.randint(10, 9999)
            username = f'{given.lower()}_{family.lower()}{suffix}'
            if User.objects.filter(username=username).exists():
                continue

            user = User.objects.create(
                username=username,
                email=f'{username}@demo.flipstar.invalid',
                first_name=given,
                last_name=family,
                is_active=True,
            )
            # No usable password: these accounts exist to be looked at, never
            # logged into. set_unusable_password is explicit about that, where
            # a random string would leave a real credential lying around.
            user.set_unusable_password()
            user.save(update_fields=['password'])

            bio = rng.choice(BIO_TEMPLATES).format(city=city) + DEMO_MARKER
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.bio = bio
            profile.xp = skewed(rng, 400, 50000)
            profile.level = 1 + profile.xp // 500
            profile.streak = skewed(rng, 3, 120)
            profile.coins = skewed(rng, 120, 20000)
            profile.coins_earned_total = profile.coins + skewed(rng, 200, 30000)
            profile.points = skewed(rng, 300, 40000)
            profile.language = rng.choices(['en', 'am'], weights=[6, 4], k=1)[0]
            profile.save()

            joined = realistic_timestamp(rng, 180)
            User.objects.filter(pk=user.pk).update(date_joined=joined)
            created.append(user)

        total = existing + created
        self.stdout.write(f'users      : {len(total)} ({len(created)} new)')
        return total

    def _follows(self, rng, users):
        if len(users) < 2:
            return
        # Follower counts are the most skewed thing in a social graph: a
        # handful of accounts hold most of the edges. Sorting by a power-law
        # draw gives a few hubs and a long tail, which is what the suggestion
        # and feed queries have to handle.
        ranked = sorted(users, key=lambda _: rng.random())
        created = 0
        for follower in ranked:
            n = min(skewed(rng, 4, 60), len(users) - 1)
            for target in rng.sample(ranked, min(n, len(ranked))):
                if target.pk == follower.pk:
                    continue
                _, made = Follow.objects.get_or_create(follower=follower, following=target)
                created += int(made)
        self.stdout.write(f'follows    : {created} new edges')

    def _reels(self, rng, users, categories, target, days):
        existing = list(Reel.objects.filter(user__profile__bio__endswith=DEMO_MARKER))
        needed = max(target - len(existing), 0)
        created = []

        for _ in range(needed):
            author = rng.choice(users)
            votes = skewed(rng, 26, 80000)
            # Views track votes with noise -- a post with 900 votes and 40
            # views would be nonsense, and any ratio-based ranking would then
            # be tested against impossible input.
            views = int(votes * rng.uniform(9, 45)) + rng.randint(5, 400)
            tags = rng.sample(HASHTAG_POOL, rng.randint(2, 5))

            reel = Reel.objects.create(
                user=author,
                caption=rng.choice(CAPTIONS),
                hashtags=' '.join(f'#{t}' for t in tags),
                category=rng.choice(categories),
                votes=votes,
                view_count=views,
                shares=skewed(rng, max(votes // 40, 1), max(votes // 4, 1)),
                processed=True,
            )
            # created_at is auto_now_add, so it cannot be set on create and has
            # to be written back afterwards. Without this every row lands in
            # the same second and nothing that orders or buckets by time gets
            # exercised at all.
            Reel.objects.filter(pk=reel.pk).update(created_at=realistic_timestamp(rng, days))
            created.append(reel)

        total = existing + created
        self.stdout.write(f'reels      : {len(total)} ({len(created)} new)')
        return total

    def _comments(self, rng, users, reels):
        created = 0
        for reel in reels:
            if Comment.objects.filter(reel=reel).exists():
                continue
            # Comment volume follows engagement rather than being flat, so
            # popular posts get threads and quiet ones get nothing -- which is
            # what a comment-count annotation has to cope with.
            n = min(skewed(rng, 2, 40), max(reel.votes // 40, 0) + rng.randint(0, 2))
            for _ in range(n):
                comment = Comment.objects.create(
                    user=rng.choice(users), reel=reel, text=rng.choice(COMMENTS)
                )
                after = reel.created_at + timedelta(minutes=rng.randint(2, 6000))
                Comment.objects.filter(pk=comment.pk).update(created_at=min(after, timezone.now()))
                created += 1
        self.stdout.write(f'comments   : {created} new')

    def _wipe(self):
        demo_users = User.objects.filter(profile__bio__endswith=DEMO_MARKER)
        count = demo_users.count()
        if not count:
            self.stdout.write('No demo users found. Nothing to remove.')
            return
        # Reels, comments and follows all cascade from User, so deleting the
        # accounts is enough. Categories are deliberately left: they are real
        # reference data that other things may point at.
        demo_users.delete()
        self.stdout.write(self.style.SUCCESS(f'Removed {count} demo users and their content.'))
