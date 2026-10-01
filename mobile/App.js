import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from "expo-audio";
import { uploadAsync, FileSystemUploadType } from "expo-file-system/legacy";
import { fetch as expoFetch } from "expo/fetch";
import Purchases, { LOG_LEVEL } from "react-native-purchases";

const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");
const RC_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_API_KEY || "";
const RC_ENTITLEMENT = process.env.EXPO_PUBLIC_REVENUECAT_ENTITLEMENT_ID || "voiceflow_pro";

const examples = [
  "Fix the checkout bug and remind me to test it tomorrow.",
  "We decided email verification is required. Tell the team on Slack.",
];

export default function App() {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [digest, setDigest] = useState(null);
  const [error, setError] = useState("");
  const [pro, setPro] = useState(false);
  const [proPrice, setProPrice] = useState("");
  const [rcReady, setRcReady] = useState(false);
  const startedAt = useRef(null);

  useEffect(() => {
    let mounted = true;
    async function configureRevenueCat() {
      if (!RC_API_KEY) return;
      try {
        Purchases.setLogLevel(LOG_LEVEL.WARN);
        await Purchases.configure({ apiKey: RC_API_KEY });
        const info = await Purchases.getCustomerInfo();
        const active = Boolean(info && info.entitlements && info.entitlements.active && info.entitlements.active[RC_ENTITLEMENT]);
        const offerings = await Purchases.getOfferings();
        const pkg = offerings && offerings.current && offerings.current.availablePackages
          ? offerings.current.availablePackages[0]
          : null;
        if (mounted) {
          setPro(active);
          setProPrice(pkg && pkg.product ? (pkg.product.priceString || "Monthly Pro") : "");
          setRcReady(true);
        }
      } catch (err) {
        console.log("RevenueCat setup:", err && err.message ? err.message : err);
      }
    }
    configureRevenueCat();
    return () => { mounted = false; };
  }, []);

  async function startRecording() {
    setError("");
    setDigest(null);
    if (!API_BASE_URL) {
      setError("Set EXPO_PUBLIC_API_BASE_URL in mobile/.env first.");
      return;
    }
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setError("Microphone permission is required to capture your thoughts.");
      return;
    }
    try {
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      startedAt.current = Date.now();
      setRecording(true);
    } catch (err) {
      setError(err && err.message ? err.message : "Could not start recording.");
    }
  }

  async function stopRecording() {
    try {
      setRecording(false);
      await recorder.stop();
      await new Promise((r) => setTimeout(r, 500));
      const uri = recorder.uri;
      if (!uri) throw new Error("No recording was produced.");
      setProcessing(true);

      const uploadResult = await uploadAsync(
        API_BASE_URL + "/mobile/process",
        uri,
        {
          httpMethod: "POST",
          uploadType: FileSystemUploadType.BINARY_CONTENT,
          headers: { "Content-Type": "audio/m4a" },
        }
      );

      const data = JSON.parse(uploadResult.body || "{}");
      if (uploadResult.status < 200 || uploadResult.status >= 300) {
        throw new Error((data && data.error) || "Voice processing failed.");
      }
      setDigest(data);
    } catch (err) {
      setError(err && err.message ? err.message : "Could not process the recording.");
    } finally {
      setProcessing(false);
    }
  }

  async function upgrade() {
    if (!rcReady) {
      Alert.alert("RevenueCat", "Add a public RevenueCat SDK key and configure an offering first.");
      return;
    }
    try {
      const offerings = await Purchases.getOfferings();
      const pkg = offerings && offerings.current && offerings.current.availablePackages
        ? offerings.current.availablePackages[0]
        : null;
      if (!pkg) {
        Alert.alert("RevenueCat", "No offering is configured yet. Create a monthly product in RevenueCat.");
        return;
      }
      const result = await Purchases.purchasePackage(pkg);
      const active = Boolean(result && result.customerInfo && result.customerInfo.entitlements
        && result.customerInfo.entitlements.active && result.customerInfo.entitlements.active[RC_ENTITLEMENT]);
      setPro(active);
    } catch (err) {
      const message = err && err.message ? err.message : String(err);
      if (!message.toLowerCase().includes("cancel")) {
        Alert.alert("Purchase", message || "Purchase could not be completed.");
      }
    }
  }

  async function restore() {
    try {
      if (!RC_API_KEY) return;
      const info = await Purchases.restorePurchases();
      const active = Boolean(info && info.entitlements && info.entitlements.active && info.entitlements.active[RC_ENTITLEMENT]);
      setPro(active);
    } catch (err) {
      Alert.alert("Restore", err && err.message ? err.message : "Could not restore purchases.");
    }
  }

  const seconds = startedAt.current && recording
    ? Math.max(1, Math.round((Date.now() - startedAt.current) / 1000))
    : 0;

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.kicker}>VOICE-FIRST ACTION LAYER</Text>
            <Text style={styles.title}>VoiceFlow AI</Text>
          </View>
          <View style={[styles.pill, pro && styles.pillPro]}>
            <Text style={styles.pillText}>{pro ? "PRO" : "FREE"}</Text>
          </View>
        </View>

        <Text style={styles.hero}>Say it once.{"\n"}We sort the rest.</Text>
        <Text style={styles.subtitle}>
          One messy thought stream becomes bugs, ideas, reminders, decisions, and explicit team messages — automatically.
        </Text>

        <View style={styles.captureCard}>
          <View style={[styles.orb, recording && styles.orbLive]}>
            {processing ? <ActivityIndicator size="large" color="#ffffff" /> : <Text style={styles.mic}>◉</Text>}
          </View>
          <Text style={styles.captureTitle}>
            {processing ? "Routing your thoughts…" : recording ? "Listening • " + seconds + "s" : "Ready when you are"}
          </Text>
          <Text style={styles.captureHint}>
            {processing ? "AssemblyAI → segment → classify → execute" : "Tap the button and speak naturally — don't structure your sentence."}
          </Text>
          <Pressable
            onPress={recording ? stopRecording : startRecording}
            disabled={processing}
            style={({ pressed }) => [styles.recordButton, recording && styles.stopButton, pressed && styles.pressed]}
          >
            <Text style={styles.recordButtonText}>{processing ? "PROCESSING" : recording ? "END CAPTURE" : "START CAPTURE"}</Text>
          </Pressable>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>TRY SAYING</Text>
          {examples.map((example) => (
            <View key={example} style={styles.example}>
              <Text style={styles.exampleText}>“{example}”</Text>
            </View>
          ))}
        </View>

        {error ? (
          <View style={styles.errorCard}><Text style={styles.errorText}>{error}</Text></View>
        ) : null}

        {digest ? (
          <View style={styles.section}>
            <View style={styles.resultsHead}>
              <Text style={styles.sectionTitle}>LIVE ROUTING RESULT</Text>
              <Text style={styles.count}>{digest.item_count} items</Text>
            </View>
            <Text style={styles.transcript}>{digest.transcript}</Text>
            {digest.items.map((item, index) => (
              <View key={item.text + "-" + index} style={styles.resultCard}>
                <View style={styles.resultTop}>
                  <Text style={styles.type}>{item.type}</Text>
                  <Text style={styles.destination}>{item.destination}</Text>
                </View>
                <Text style={styles.resultText}>{item.text}</Text>
                {item.url ? (
                  <Pressable
                    onPress={() => Linking.openURL(item.url)}
                    style={styles.linkButton}
                  >
                    <Text style={styles.linkText}>
                      Open {item.destination ? item.destination.toUpperCase() : "LINK"} ↗
                    </Text>
                  </Pressable>
                ) : null}
                {item.detail ? (
                  <Text style={styles.detailText}>{item.detail}</Text>
                ) : null}
                <Text style={styles.resultMeta}>
                  {item.status} • confidence {Number(item.confidence || 0).toFixed(2)}
                </Text>
              </View>
            ))}
          </View>
        ) : null}

        <View style={styles.proCard}>
          <View style={{ flex: 1 }}>
            <Text style={styles.proKicker}>REVENUECAT POWERED</Text>
            <Text style={styles.proTitle}>VoiceFlow Pro</Text>
            <Text style={styles.proText}>Unlimited captures, priority processing, and saved routing preferences.</Text>
            {proPrice ? <Text style={styles.price}>{proPrice} / month</Text> : null}
          </View>
          <Pressable onPress={pro ? restore : upgrade} style={styles.upgradeButton}>
            <Text style={styles.upgradeText}>{pro ? "RESTORE" : "UPGRADE"}</Text>
          </Pressable>
        </View>

        <Text style={styles.footer}>
          Your action credentials stay on the backend. The mobile client sends only the recording and receives the result.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#07111f" },
  container: { padding: 22, paddingBottom: 48 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 28 },
  kicker: { color: "#78a8d8", fontSize: 10, fontWeight: "700", letterSpacing: 2.2 },
  title: { color: "#f6f9ff", fontSize: 27, fontWeight: "800", marginTop: 4 },
  pill: { borderWidth: 1, borderColor: "#29435f", backgroundColor: "#0d1c2d", borderRadius: 999, paddingHorizontal: 11, paddingVertical: 7 },
  pillPro: { borderColor: "#6d8cff", backgroundColor: "#182449" },
  pillText: { color: "#d9e5f7", fontSize: 10, fontWeight: "800", letterSpacing: 1.4 },
  hero: { color: "#ffffff", fontSize: 40, lineHeight: 44, fontWeight: "800", letterSpacing: -1.3 },
  subtitle: { color: "#9eb1c8", fontSize: 15, lineHeight: 23, marginTop: 14, marginBottom: 24 },
  captureCard: { backgroundColor: "#0b1929", borderColor: "#1f344b", borderWidth: 1, borderRadius: 28, alignItems: "center", padding: 28 },
  orb: { width: 112, height: 112, borderRadius: 56, backgroundColor: "#285fca", justifyContent: "center", alignItems: "center", marginBottom: 18 },
  orbLive: { backgroundColor: "#c54b55" },
  mic: { color: "#ffffff", fontSize: 44 },
  captureTitle: { color: "#ffffff", fontSize: 21, fontWeight: "800" },
  captureHint: { color: "#8ea2ba", textAlign: "center", fontSize: 13, lineHeight: 19, marginTop: 7, maxWidth: 300 },
  recordButton: { marginTop: 21, width: "100%", height: 48, borderRadius: 14, backgroundColor: "#3678e5", alignItems: "center", justifyContent: "center" },
  stopButton: { backgroundColor: "#c54b55" },
  pressed: { opacity: 0.78 },
  recordButtonText: { color: "#ffffff", fontWeight: "800", fontSize: 12, letterSpacing: 1.5 },
  section: { marginTop: 26 },
  sectionTitle: { color: "#7089a6", fontSize: 10, fontWeight: "800", letterSpacing: 1.8 },
  example: { backgroundColor: "#0b1929", borderColor: "#1b3048", borderWidth: 1, borderRadius: 15, padding: 15, marginTop: 10 },
  exampleText: { color: "#b9c8da", fontSize: 14, lineHeight: 20 },
  errorCard: { marginTop: 18, backgroundColor: "#2b161b", borderColor: "#77303a", borderWidth: 1, borderRadius: 14, padding: 14 },
  errorText: { color: "#ffb7be", lineHeight: 20, fontSize: 13 },
  resultsHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  count: { color: "#7190b5", fontSize: 11 },
  transcript: { color: "#8da0b8", marginTop: 10, lineHeight: 19, fontSize: 12 },
  resultCard: { backgroundColor: "#0b1929", borderRadius: 15, borderColor: "#1b3048", borderWidth: 1, padding: 15, marginTop: 10 },
  resultTop: { flexDirection: "row", justifyContent: "space-between", marginBottom: 7 },
  type: { color: "#82a7dd", fontSize: 10, fontWeight: "800", textTransform: "uppercase", letterSpacing: 1.2 },
  destination: { color: "#6fe0b5", fontSize: 10, fontWeight: "800", textTransform: "uppercase", letterSpacing: 1.1 },
  resultText: { color: "#eef4fb", fontSize: 14, lineHeight: 21 },
  resultMeta: { color: "#677f9c", marginTop: 8, fontSize: 11 },
  linkButton: { marginTop: 10, alignSelf: "flex-start", backgroundColor: "#1c324c", borderWidth: 1, borderColor: "#35577f", paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8 },
  linkText: { color: "#78b2ff", fontSize: 12, fontWeight: "700" },
  detailText: { color: "#8ea2ba", marginTop: 6, fontSize: 11 },
  proCard: { marginTop: 28, backgroundColor: "#101c35", borderRadius: 20, borderWidth: 1, borderColor: "#31466e", padding: 19, flexDirection: "row", gap: 14, alignItems: "center" },
  proKicker: { color: "#86a9ff", fontSize: 9, fontWeight: "800", letterSpacing: 1.5 },
  proTitle: { color: "#ffffff", fontSize: 20, fontWeight: "800", marginTop: 3 },
  proText: { color: "#9aabd0", fontSize: 12, lineHeight: 18, marginTop: 5 },
  price: { color: "#dfe6ff", marginTop: 8, fontSize: 12, fontWeight: "700" },
  upgradeButton: { backgroundColor: "#ffffff", borderRadius: 11, paddingHorizontal: 14, paddingVertical: 12 },
  upgradeText: { color: "#142449", fontSize: 10, fontWeight: "900", letterSpacing: 1 },
  footer: { color: "#52677f", textAlign: "center", fontSize: 10, lineHeight: 15, marginTop: 22 },
});
