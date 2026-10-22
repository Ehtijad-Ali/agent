"""US city reference data for content agents (brief §2.2, §2.5).

A static table rather than a geocoding API, because the brief forbids extra
recurring bills and this needs only a city, its state and one plausible ZIP.
Each ZIP is a real central code for that city, so an ad filled from this table
is internally consistent.

Not exhaustive by design: 48 cities is more than a human will post to by hand,
and the "never reuse a city" rule means the table also caps how many ads an
agent can ever generate -- which is a useful brake, not a limitation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class City:
    name: str
    state: str
    state_code: str
    zipcode: str

    @property
    def key(self) -> str:
        """Stable uniqueness key, used by the "not used before" constraint."""
        return f"US:{self.state_code}:{self.name}"


US_CITIES: tuple[City, ...] = (
    City("Phoenix", "Arizona", "AZ", "85004"),
    City("Tucson", "Arizona", "AZ", "85701"),
    City("Los Angeles", "California", "CA", "90012"),
    City("San Diego", "California", "CA", "92101"),
    City("San Jose", "California", "CA", "95113"),
    City("Sacramento", "California", "CA", "95814"),
    City("Fresno", "California", "CA", "93721"),
    City("Denver", "Colorado", "CO", "80202"),
    City("Colorado Springs", "Colorado", "CO", "80903"),
    City("Jacksonville", "Florida", "FL", "32202"),
    City("Miami", "Florida", "FL", "33130"),
    City("Tampa", "Florida", "FL", "33602"),
    City("Orlando", "Florida", "FL", "32801"),
    City("Atlanta", "Georgia", "GA", "30303"),
    City("Chicago", "Illinois", "IL", "60601"),
    City("Indianapolis", "Indiana", "IN", "46204"),
    City("Wichita", "Kansas", "KS", "67202"),
    City("Louisville", "Kentucky", "KY", "40202"),
    City("New Orleans", "Louisiana", "LA", "70112"),
    City("Baltimore", "Maryland", "MD", "21202"),
    City("Boston", "Massachusetts", "MA", "02108"),
    City("Detroit", "Michigan", "MI", "48226"),
    City("Minneapolis", "Minnesota", "MN", "55401"),
    City("Kansas City", "Missouri", "MO", "64106"),
    City("St. Louis", "Missouri", "MO", "63101"),
    City("Omaha", "Nebraska", "NE", "68102"),
    City("Las Vegas", "Nevada", "NV", "89101"),
    City("Newark", "New Jersey", "NJ", "07102"),
    City("Albuquerque", "New Mexico", "NM", "87102"),
    City("New York", "New York", "NY", "10007"),
    City("Buffalo", "New York", "NY", "14202"),
    City("Charlotte", "North Carolina", "NC", "28202"),
    City("Raleigh", "North Carolina", "NC", "27601"),
    City("Columbus", "Ohio", "OH", "43215"),
    City("Cleveland", "Ohio", "OH", "44113"),
    City("Cincinnati", "Ohio", "OH", "45202"),
    City("Oklahoma City", "Oklahoma", "OK", "73102"),
    City("Portland", "Oregon", "OR", "97204"),
    City("Philadelphia", "Pennsylvania", "PA", "19107"),
    City("Pittsburgh", "Pennsylvania", "PA", "15222"),
    City("Nashville", "Tennessee", "TN", "37201"),
    City("Memphis", "Tennessee", "TN", "38103"),
    City("Houston", "Texas", "TX", "77002"),
    City("San Antonio", "Texas", "TX", "78205"),
    City("Dallas", "Texas", "TX", "75201"),
    City("Austin", "Texas", "TX", "78701"),
    City("Salt Lake City", "Utah", "UT", "84111"),
    City("Seattle", "Washington", "WA", "98104"),
)

CITIES_BY_KEY: dict[str, City] = {city.key: city for city in US_CITIES}
