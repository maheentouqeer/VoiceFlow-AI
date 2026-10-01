# VoiceFlow AI Mobile

A student-focused mobile version of VoiceFlow AI for RevenueCat Shipaton 2026.

## What it does

Speak naturally about multiple things in one capture. VoiceFlow AI sends the recording to the secure backend, transcribes it with AssemblyAI, segments the transcript, classifies each thought, and executes the existing GitHub, Todoist, Notion, and explicit-Slack routing rules.

The app also includes a RevenueCat-powered Pro subscription surface for the Shipaton integration.

## Run locally

1. Install Node.js 20+.
2. Copy the .env.example file to .env and set EXPO_PUBLIC_API_BASE_URL to your deployed VoiceFlow backend.
3. Add your RevenueCat public SDK key as EXPO_PUBLIC_REVENUECAT_API_KEY.
4. From this directory run:

    npm install
    npx expo start

Scan the QR code with Expo Go to test the core mobile workflow. RevenueCat documents an Expo Go Preview API Mode for subscription logic; a development build is required for real store billing.

## RevenueCat setup

Create a RevenueCat project, add an Android or iOS app, create an entitlement named voiceflow_pro, create a monthly product/offering, and put the public SDK key in .env.

Do not put AssemblyAI, GitHub, Todoist, Notion, or Slack secrets in the mobile app.
