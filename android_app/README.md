# ANILNEWSFO Android app

Native Android starter for the ANILNEWSFO market-intelligence pipeline.

## Current version
- 📰 News feed
- 📊 F&O candidate feed
- 🔥 Breakout Watch tab
- Reads the latest structured feed from the public GitHub repository
- Refreshes on app launch or with the refresh button

## Data flow

GitHub Actions → data/app_feed.json → Android app

The feed contains no API secrets. The existing market/F&O engine remains in Python.

## Build
Open the `android_app` folder in Android Studio and sync Gradle.

The project uses Android Gradle Plugin 9.4.0 and JDK 17.
