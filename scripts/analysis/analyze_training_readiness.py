"""Audit local HotelRec subsets without third-party dependencies.

Input is a JSON array with one review object per line (the local export format).
Author strings are treated as identifiers; their real-world identity is unverified.
K-core counts unique user-hotel edges, not repeated reviews. No raw authors or
review text are written to the aggregate output.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import re


def kcore(users, k):
    active = {u: set(hs) for u, hs in users.items() if len(hs) >= k}
    rounds = 0
    while True:
        degrees = Counter(h for hs in active.values() for h in hs)
        keep = {h for h, degree in degrees.items() if degree >= k}
        reduced = {u: hs & keep for u, hs in active.items()}
        reduced = {u: hs for u, hs in reduced.items() if len(hs) >= k}
        rounds += 1
        if reduced == active:
            break
        active = reduced
    hotels = {h for hs in active.values() for h in hs}
    return dict(users=len(active), hotels=len(hotels),
                unique_interactions=sum(map(len, active.values())), rounds=rounds)


def analyze(path):
    users = defaultdict(set)
    positive = defaultdict(set)
    dates = defaultdict(set)
    hotel_reviews = Counter()
    ratings, years, fields, missing = Counter(), Counter(), Counter(), Counter()
    subratings = Counter()
    subrating_sums = Counter()
    date_min, date_max = None, None
    n = invalid = valid_edges = 0
    with path.open(encoding='utf-8') as source:
        for lineno, line in enumerate(source, 1):
            line = line.strip()
            if line in ('', '[', ']'):
                continue
            try:
                record = json.loads(line.rstrip(','))
            except json.JSONDecodeError as error:
                raise ValueError(f'{path}:{lineno}: invalid review JSON') from error
            n += 1
            fields.update(record.keys())
            match = re.search(r'-d(\d+)-', record.get('hotel_url') or '')
            hotel = match.group(1) if match else None
            author = record.get('author')
            date = record.get('date')
            rating = record.get('rating')
            for key in ('author', 'date', 'rating', 'text', 'hotel_url'):
                if record.get(key) in (None, ''):
                    missing[key] += 1
            if hotel:
                hotel_reviews[hotel] += 1
            if author and hotel:
                users[author].add(hotel)
                valid_edges += 1
                if isinstance(rating, (int, float)) and rating >= 4:
                    positive[author].add(hotel)
            if isinstance(rating, (int, float)):
                ratings[str(rating)] += 1
            try:
                parsed = datetime.fromisoformat(date)
                years[str(parsed.year)] += 1
                normalized = parsed.isoformat()
                date_min = min(date_min or normalized, normalized)
                date_max = max(date_max or normalized, normalized)
                if author and hotel:
                    dates[author].add(normalized)
            except (ValueError, TypeError):
                invalid += 1
            for key, value in (record.get('property_dict') or {}).items():
                if isinstance(value, (int, float)):
                    subratings[key] += 1
                    subrating_sums[key] += value
    lengths = Counter(map(len, users.values()))
    edges = sum(map(len, users.values()))
    placeholders = {'/undefined', 'null'}
    clean_users = {u: hs for u, hs in users.items() if u not in placeholders}
    result = {
        'input': str(path.resolve()), 'reviews': n,
        'hotels': len(hotel_reviews), 'author_identifiers': len(users),
        'unique_user_hotel_edges': edges,
        'repeat_user_hotel_review_rows': valid_edges - edges,
        'unique_hotels_per_user_histogram': dict(sorted(lengths.items())),
        'users_by_min_unique_hotels': {
            str(k): sum(v for length, v in lengths.items() if length >= k)
            for k in (1, 2, 3, 5, 10, 20)},
        'users_with_at_least_3_distinct_review_timestamps':
            sum(len(ds) >= 3 for ds in dates.values()),
        'positive_rating_ge4_users_by_min_unique_hotels': {
            str(k): sum(len(hs) >= k for hs in positive.values())
            for k in (3, 5, 10)},
        'date_min': date_min, 'date_max': date_max,
        'invalid_dates': invalid, 'missing_fields': dict(missing),
        'field_presence': dict(fields), 'rating_counts': dict(ratings),
        'year_counts': dict(sorted(years.items())),
        'hotel_review_thresholds': {
            str(k): sum(v >= k for v in hotel_reviews.values())
            for k in (5, 20, 100)},
        'subratings': {key: {'reviews': count, 'coverage': count / n,
                            'mean': subrating_sums[key] / count}
                       for key, count in subratings.most_common()},
        'excluded_author_placeholders': {
            u: {'distinct_hotels': len(users[u])}
            for u in placeholders if u in users},
        'usable_author_identifiers': len(clean_users),
        'usable_users_by_min_unique_hotels': {
            str(k): sum(len(hs) >= k for hs in clean_users.values())
            for k in (1, 2, 3, 5, 10, 20)},
        'usable_positive_users_by_min_unique_hotels': {
            str(k): sum(len(hs) >= k for u, hs in positive.items()
                        if u not in placeholders)
            for k in (3, 5, 10)},
        'unique_edge_kcore': {str(k): kcore(clean_users, k) for k in (3, 5, 10)},
        'notes': [
            'Author strings are unverified identity proxies.',
            'Known literal author placeholders /undefined and null excluded from usable and k-core counts.',
            'Repeat user-hotel rows are not necessarily duplicate reviews.',
            'K-core uses unique edges, before any temporal train/test split.',
            'Timestamp threshold alone does not guarantee distinct-hotel sequences.',
            'Positive-user counts do not apply iterative item filtering.'],
    }
    assert sum(lengths.values()) == len(users)
    assert sum(length * count for length, count in lengths.items()) == edges
    assert sum(hotel_reviews.values()) <= n
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = []
    for path in args.input:
        result = analyze(path)
        results.append(result)
        print(json.dumps({k: result[k] for k in (
            'input', 'reviews', 'hotels', 'author_identifiers',
            'users_by_min_unique_hotels', 'unique_edge_kcore')}, ensure_ascii=False),
            flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')


if __name__ == '__main__':
    main()
