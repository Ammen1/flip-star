import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, Modal, ActivityIndicator, KeyboardAvoidingView,
  Platform, StatusBar, Image, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../../contexts/AuthContext';
import api from '../../api';
import config from '../../config';
import ForgotPasswordPhone from './ForgotPasswordPhone';
import SubscriptionRegisterModal from './SubscriptionRegisterModal';
import SubscriptionPlansModal from './SubscriptionPlansModal';
import Svg, { Line, Path } from 'react-native-svg';
import { LinearGradient } from 'expo-linear-gradient';

const GOLD = '#D4AF37'; // Gold brand color
const BG = '#000000'; // Black background
const CARD = '#1A1A1A'; // Dark gray for cards
const BORDER = '#333333'; // Dark border

const FAQ_ITEMS = [
  { 
    q: "What is FlipStar?", 
    a: "FlipStar is a premium, subscription-based gamified social media platform by Ethio Telecom and Skykin Technologies PLC. Upload short videos and photos ('Flips'), compete in campaigns, earn coins, and participate in a creator economy powered by telebirr." 
  },
  { 
    q: "Who can use FlipStar?", 
    a: "All active Ethio Telecom prepaid, postpaid, and hybrid mobile customers with a smartphone (Android, iOS) or web browser. Users must be at least 13 years old. For claiming prizes, users must be 18 or older." 
  },
  { 
    q: "What devices and platforms does FlipStar support?", 
    a: "Android App: Available on Google Play Store (search: FlipStar). iOS App: Available on Apple App Store (search: FlipStar). Web: Visit https://flipstar.et in any modern browser." 
  },
  { 
    q: "Is FlipStar available to all Ethio Telecom customers?", 
    a: "Yes. All active prepaid, postpaid, and hybrid Ethio Telecom mobile customers can subscribe and use the service. The subscriber's number must be in 'Active' status at the time of subscription." 
  },
  { 
    q: "How do I subscribe to FlipStar?", 
    a: "Via SMS: Send 'OK1' (Daily), 'OK2' (Weekly), or 'OK3' (Monthly) to the FlipStar shortcode. Via App/Web: Download the app or visit https://flipstar.et, select 'Sign Up', enter your full name and mobile number, then enter the confirmation code sent to your number." 
  },
  { 
    q: "What subscription plans are available?", 
    a: "Daily Plan: 3 ETB per day • Weekly Plan: 20 ETB per week • Monthly Plan: 70 ETB per month • Yearly Plan: 600 ETB per year • On-Demand: 10 ETB for 100 Coins (one-time purchase)." 
  },
  { 
    q: "Is there a free trial?", 
    a: "Yes. New subscribers receive a 1-day (24-hour) free trial on their first subscription. Re-subscribers who previously used the trial are not eligible for another." 
  },
  { 
    q: "How am I charged?", 
    a: "Prepaid: fee deducted from airtime balance. Postpaid: fee added to monthly bill. Hybrid: charged from your default account. A maximum of one charge applies per 24-hour cycle. Failed charges are retried automatically if you recharge the same day." 
  },
  { 
    q: "How do I unsubscribe?", 
    a: "Send 'STOP1' (Daily), 'STOP2' (Weekly), or 'STOP3' (Monthly) to the FlipStar shortcode, or go to Account Settings in the app and select Unsubscribe. Your request is processed immediately and you will receive a confirmation SMS." 
  },
  { 
    q: "What happens to my coins and progress if I unsubscribe?", 
    a: "Your coins and digital assets remain valid for 30 days after unsubscription. Re-subscribing within 30 days restores your unexpired coins and progress. Assets not recovered within 30 days will expire." 
  },
  { 
    q: "What are coins and how do I earn them?", 
    a: "Coins are FlipStar's digital currency. Earn them through: Daily login bonus (3 coins/day), Weekly loyalty bonus (50 coins for 7-day streak), Monthly bonus (200 coins for 30-day active streak), or Purchase via telebirr/Airtime." 
  },
  { 
    q: "What can I do with coins?", 
    a: "Gift creators, boost your content visibility, unlock extended video uploads (up to 90-120 seconds), level up, and unlock premium features." 
  },
  { 
    q: "Can I cash out my coins?", 
    a: "Bonus coins (from login/loyalty) cannot be cashed out. However, Points earned by creators from gifts can be cashed out via telebirr. Minimum: 1,000 Points (80 ETB after 20% commission)." 
  },
  { 
    q: "What is the platform commission?", 
    a: "A 20% commission applies to all gifting transaction payouts. For example: if a creator earns 1,000 Points, 200 Points (20%) are retained as platform commission, and the creator receives 800 Points (80 ETB) via telebirr." 
  },
  { 
    q: "Can I convert my Points back into Coins?", 
    a: "Yes. The swap rate is 1 Point = 1 Coin. You can use earned Points to purchase more Coins for in-app spending instead of cashing out." 
  },
  { 
    q: "What is a Flip and how do I upload one?", 
    a: "A Flip is a short video (15–120 seconds) or photo you upload to the platform. Tap the '+' button, select or record your content, add a caption and hashtags, optionally link it to a campaign, and tap 'Post'." 
  },
  { 
    q: "How long can my videos be?", 
    a: "Standard subscribers: 15 to 60 seconds. Coin buyers (On-Demand / premium): up to 90–120 seconds." 
  },
  { 
    q: "What are the competition prizes?", 
    a: "Daily Sprint (50 winners): 1GB data • Weekly Battle (10 winners): 1,000 ETB • Monthly Star (5 winners): 10,000 ETB • Grand Final: 1st-500,000 ETB, 2nd-300,000 ETB, 3rd-200,000 ETB." 
  },
  { 
    q: "How is my competition score calculated?", 
    a: "Score = (Likes × 1) + (Comments × 2) + (Shares × 5) + (Gift/Vote Points × 10). The highest Engagement Score wins each tier." 
  },
  { 
    q: "Can I win multiple prizes?", 
    a: "Yes, with rules. After winning a tier, you're ineligible for that same tier for 30 days. You can still win other tiers during the cooldown. Eligibility restores after 30 days." 
  },
  { 
    q: "How do I claim my prize?", 
    a: "Cash prizes (ETB): sent automatically via telebirr. Daily Data prizes: credited to your Ethio Telecom account within 24 hours. Grand Final prizes: our team will contact you — you must present a valid National ID or passport. All prizes must be claimed within 30 days of notification." 
  },
  { 
    q: "Is there a daily voting limit for one creator?", 
    a: "Yes. A single user can contribute a maximum of 5,000 Score Points (equivalent to 500 Coins) per day to any one specific creator. This Voting Cap prevents pay-to-win behaviour and protects competition integrity." 
  },
  { 
    q: "Do boosted views count toward my leaderboard score?", 
    a: "No. Views and impressions from paid content boosts (Standard, Premium, or Viral Boost) do not count toward your organic Engagement Score. Only genuine, unboosted engagement contributes to your score." 
  },
  { 
    q: "Are there internet data charges for using FlipStar?", 
    a: "Yes. Accessing FlipStar via the app or web portal at https://flipstar.et uses your regular Ethio Telecom data plan. You are responsible for any data charges incurred." 
  },
  { 
    q: "Is my personal data safe?", 
    a: "Yes. FlipStar is hosted on Ethio Telecom InfraCloud within Ethiopia. Your phone number is encrypted and never displayed publicly. All personal metadata is removed from uploads." 
  },
  { 
    q: "Can Ethio Telecom change the Terms or cancel the service?", 
    a: "Yes. Ethio Telecom reserves the right to modify, suspend, or terminate the FlipStar service at any time in accordance with Ethiopian laws. Changes will be published at https://flipstar.et. Continued use after changes take effect constitutes acceptance." 
  },
  { 
    q: "How do I contact support?", 
    a: "In-App: Profile → Help & Support • Email: support@flipstar.et • SMS: 8994 • WhatsApp: +251 99 400 0000 • Telegram: t.me/ethio_telecom • Web: ethiotelecom.et" 
  },
];

// ── Terms table helper ─────────────────────────────────────────────────────
function TermsTable({ headers, rows, flex }) {
  const colFlex = flex || headers.map(() => 1);
  return (
    <View style={ts.table}>
      <View style={[ts.row, ts.headerRow]}>
        {headers.map((h, i) => (
          <Text key={i} style={[ts.cell, ts.headerCell, { flex: colFlex[i] }]}>{h}</Text>
        ))}
      </View>
      {rows.map((row, ri) => (
        <View key={ri} style={[ts.row, ri % 2 === 1 && ts.altRow]}>
          {row.map((cell, ci) => (
            <Text key={ci} style={[ts.cell, ts.dataCell, { flex: colFlex[ci] }]}>{cell}</Text>
          ))}
        </View>
      ))}
    </View>
  );
}

const ts = StyleSheet.create({
  para:           { fontSize: 11, color: '#ccc', lineHeight: 17, marginBottom: 8 },
  sectionTitle:   { fontSize: 13, fontWeight: '800', color: GOLD, marginTop: 16, marginBottom: 6 },
  subSectionTitle:{ fontSize: 12, fontWeight: '700', color: '#ddd', marginTop: 10, marginBottom: 4 },
  bullet:         { fontSize: 11, color: '#bbb', lineHeight: 17, marginBottom: 4, paddingLeft: 4 },
  table:          { borderWidth: 1, borderColor: '#333', borderRadius: 6, marginBottom: 12, overflow: 'hidden' },
  row:            { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: '#222' },
  headerRow:      { backgroundColor: '#1A1A1A' },
  altRow:         { backgroundColor: '#111' },
  cell:           { padding: 6, fontSize: 10, color: '#ccc', lineHeight: 14 },
  headerCell:     { color: GOLD, fontWeight: '700', fontSize: 10 },
  dataCell:       {},
  infoBox:        { backgroundColor: '#1A1A2E', borderLeftWidth: 3, borderLeftColor: GOLD, padding: 10, borderRadius: 6, marginBottom: 10 },
  infoText:       { fontSize: 11, color: '#aaa', lineHeight: 16 },
  formulaBox:     { backgroundColor: '#0D1A2B', borderWidth: 1, borderColor: GOLD, padding: 12, borderRadius: 8, marginBottom: 8 },
  formulaText:    { fontSize: 11, color: GOLD, fontWeight: '600', textAlign: 'center' },
});

// ── FAQ Modal ──────────────────────────────────────────────────────────────
function FaqModal({ onClose }) {
  const [open, setOpen] = useState(null);
  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <View style={s.modalOverlay}>
        <View style={s.modalSheet}>
          <View style={s.modalHeader}>
            <Text style={s.modalTitle}>FAQ</Text>
            <TouchableOpacity onPress={onClose}><Ionicons name="close" size={22} color={GOLD} /></TouchableOpacity>
          </View>
          <ScrollView>
            {FAQ_ITEMS.map((item, i) => (
              <View key={i} style={s.faqItem}>
                <TouchableOpacity style={s.faqQ} onPress={() => setOpen(open === i ? null : i)}>
                  <Text style={s.faqQText}>{item.q}</Text>
                  <Ionicons name={open === i ? 'chevron-up' : 'chevron-down'} size={16} color={GOLD} />
                </TouchableOpacity>
                {open === i && <Text style={s.faqA}>{item.a}</Text>}
              </View>
            ))}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

// ── Terms Modal ────────────────────────────────────────────────────────────
function TermsModal({ onClose }) {
  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <View style={[s.modalOverlay, { justifyContent: 'flex-start' }]}>
        <View style={[s.modalSheet, { maxHeight: '100%', minHeight: '100%', borderRadius: 0, paddingTop: 48 }]}>
          <View style={s.modalHeader}>
            <Text style={s.modalTitle}>Terms & Conditions</Text>
            <TouchableOpacity onPress={onClose}><Ionicons name="close" size={22} color={GOLD} /></TouchableOpacity>
          </View>
          <ScrollView showsVerticalScrollIndicator={false} style={{ padding: 4 }}>

            {/* Preamble */}
            <Text style={ts.para}>Please read these Terms and Conditions ("Terms") carefully before using the FlipStar service ("FlipStar", "the Service") provided by Ethio Telecom and SkykinTechnologies PLC ("the Providers"). These Terms apply to all visitors, users, and others who access or use the Service via the FlipStar mobile application (Android and iOS) or web portal at https://flipstar.et.</Text>
            <Text style={ts.para}>By subscribing, downloading, installing, or otherwise accessing FlipStar, you acknowledge that you have read, understood, and agree to be bound by these Terms. If you do not agree, do not use the Service.</Text>

            {/* 1 */}
            <Text style={ts.sectionTitle}>1. Introduction</Text>
            <Text style={ts.para}>FlipStar is a premium, subscription-based gamified social media platform developed for Ethio Telecom customers. The platform enables users to create, share, and discover short-form videos and photos ('Flips'), participate in competitive campaigns, earn rewards, and engage in a digital creator economy powered by the telebirr wallet.</Text>
            <Text style={ts.para}>FlipStar is accessible via:</Text>
            <Text style={ts.bullet}>• Web Portal: https://flipstar.et</Text>
            <Text style={ts.bullet}>• Android App: Available on Google Play Store (search: FlipStar)</Text>
            <Text style={ts.bullet}>• iOS App: Available on Apple App Store (search: FlipStar)</Text>

            {/* 2 */}
            <Text style={ts.sectionTitle}>2. Service Overview</Text>
            <Text style={ts.bullet}>• FlipStar is available to all active Ethio Telecom prepaid, postpaid, and hybrid mobile customers with a smartphone device (Android, iOS, or any HTML5-capable browser for web access).</Text>
            <Text style={ts.bullet}>• The Service allows users to upload short-form videos (15–120 seconds depending on user tier) and photos, interact with content, participate in daily, weekly, monthly, and grand prize competitions, and earn and spend digital coins.</Text>
            <Text style={ts.bullet}>• To subscribe via SMS: send 'OK1' (Daily), 'OK2' (Weekly), or 'OK3' (Monthly) to the FlipStar shortcode. To unsubscribe: send 'STOP1', 'STOP2', or 'STOP3' to the same shortcode.</Text>
            <Text style={ts.bullet}>• To subscribe via app or web: download the FlipStar app or visit https://flipstar.et, select Sign Up, and follow the on-screen registration flow.</Text>

            {/* 3 */}
            <Text style={ts.sectionTitle}>3. Subscription and Billing</Text>
            <Text style={ts.subSectionTitle}>3.1 Subscription Plans</Text>
            <TermsTable
              headers={['Plan', 'Price', 'Billing Cycle', 'Notes']}
              flex={[1.1, 0.9, 1, 1.5]}
              rows={[
                ['Daily Plan', '3 ETB', 'Every 24 hrs', 'Charged daily. Auto-renewed while active.'],
                ['Weekly Plan', '20 ETB', 'Every 7 days', 'Charged weekly. Auto-renewed while active.'],
                ['Monthly Plan', '70 ETB', 'Every 30 days', 'Charged monthly. Auto-renewed while active.'],
                ['On-Demand Plan', '10 ETB / 100 Coins', 'One-time', 'Coins on demand. No recurring charge.'],
              ]}
            />
            <Text style={ts.subSectionTitle}>3.2 Eligibility</Text>
            <Text style={ts.bullet}>• All active prepaid, postpaid, and hybrid Ethio Telecom mobile customers are eligible to subscribe.</Text>
            <Text style={ts.bullet}>• The subscriber's service number must be in 'Active' status at the time of subscription.</Text>
            <Text style={ts.bullet}>• After any applicable free trial period, the subscriber must have sufficient balance to continue service.</Text>
            <Text style={ts.subSectionTitle}>3.3 Free Trial</Text>
            <Text style={ts.bullet}>• New subscribers receive a 1-day (24-hour) free trial on their first-time subscription.</Text>
            <Text style={ts.bullet}>• The free trial is available for first-time subscribers only. Users who have previously subscribed and cancel are not eligible for a second free trial upon re-subscription.</Text>
            <Text style={ts.subSectionTitle}>3.4 Charging Logic</Text>
            <Text style={ts.bullet}>• Prepaid customers: Subscription fees are deducted from the current airtime balance.</Text>
            <Text style={ts.bullet}>• Postpaid customers: Subscription fees are added to the monthly bill.</Text>
            <Text style={ts.bullet}>• Hybrid customers: Fees are charged from the default account.</Text>
            <Text style={ts.bullet}>• A maximum of one subscription charge per 24-hour cycle applies.</Text>
            <Text style={ts.bullet}>• Failed billing attempts will be retried automatically per Ethio Telecom MA time standards, or if the customer recharges their balance within the same day.</Text>
            <Text style={ts.bullet}>• The service will be activated automatically after a successful subscription or payment.</Text>
            <Text style={ts.subSectionTitle}>3.5 Auto-Renewal</Text>
            <Text style={ts.bullet}>• FlipStar subscriptions auto-renew at the end of each billing cycle if the subscriber has sufficient balance.</Text>
            <Text style={ts.bullet}>• Upon successful renewal, the subscriber will receive an SMS notification confirming the renewal and extended service period.</Text>
            <Text style={ts.bullet}>• If auto-renewal fails due to insufficient balance, service access may be suspended until the next successful charge or manual resubscription.</Text>
            <Text style={ts.subSectionTitle}>3.6 Unsubscription</Text>
            <Text style={ts.bullet}>• To unsubscribe, send 'STOP1', 'STOP2', or 'STOP3' to the FlipStar shortcode, or use the unsubscription option within the app or web portal under Account Settings.</Text>
            <Text style={ts.bullet}>• Unsubscription requests are processed immediately.</Text>
            <Text style={ts.bullet}>• A subscriber is considered active until they explicitly unsubscribe. Once cancelled, the user must re-subscribe to regain access to premium features.</Text>
            <Text style={ts.bullet}>• Coins and digital assets earned or purchased prior to unsubscription remain valid for 30 days and are restored upon re-subscription within that period if not expired.</Text>
            <View style={ts.infoBox}>
              <Text style={ts.infoText}>ⓘ SMS Notifications: You will receive an automatic SMS for successful subscription, successful unsubscription, and each auto-renewal.</Text>
            </View>

            {/* 4 */}
            <Text style={ts.sectionTitle}>4. Accounts</Text>
            <Text style={ts.bullet}>• Once you subscribe via SMS or complete registration via the app or web portal, FlipStar will automatically create an account using your Ethio Telecom mobile number as your unique account identifier.</Text>
            <Text style={ts.bullet}>• By accessing the service, you agree to be solely responsible for all activities that occur under your account and mobile number.</Text>
            <Text style={ts.bullet}>• You agree to provide true, current, and complete information during registration and at all times during your use of the service.</Text>
            <Text style={ts.bullet}>• Only one active account per mobile number is permitted.</Text>

            {/* 5 */}
            <Text style={ts.sectionTitle}>5. Digital Coins and the Creator Economy</Text>
            <Text style={ts.subSectionTitle}>5.1 Coins Overview</Text>
            <Text style={ts.para}>FlipStar operates a digital coin system that powers the platform's creator economy. Coins are the platform's internal currency used for content interaction, gifting, and access to premium features.</Text>
            <TermsTable
              headers={['Action', 'Rate / Rule']}
              flex={[1, 1.8]}
              rows={[
                ['Purchase coins', 'Purchase coins via telebirr or Airtime. No commission at purchase.'],
                ['On-Demand Pack', '10 ETB = 100 Coins (Flip On-Demand purchase).'],
                ['Daily login bonus', '3 Coins per day for opening the FlipStar app.'],
                ['Weekly loyalty bonus', '50 Coins for consistent daily usage for a full week.'],
                ['Gift a creator', 'Convert Coins into virtual Gifts sent to other users\' content.'],
                ['Creator earns Points', '1 Coin gifted = 1 Point earned (100% of gift value).'],
                ['Cash out Points', '10 Points = 0.8 ETB (20% platform commission at payout).'],
                ['Re-invest Points', '1 Point = 1 Coin (swap Points back to Coins for in-app spending).'],
                ['Min. cash-out', '1,000 Points (80 ETB net after commission) required for telebirr payout.'],
              ]}
            />
            <Text style={ts.subSectionTitle}>5.2 Coin Rules</Text>
            <Text style={ts.bullet}>• Coins purchased via telebirr or Airtime have no expiry when actively used. Coins not used or converted within 30 days of purchase may expire.</Text>
            <Text style={ts.bullet}>• Points not withdrawn or converted within 180 days of account inactivity are forfeited.</Text>
            <Text style={ts.bullet}>• All coin purchases are non-refundable once processed.</Text>
            <Text style={ts.bullet}>• Coins earned via daily bonuses and loyalty rewards may not be cashed out — they may only be spent within the platform (gifting, boosts, etc.).</Text>
            <Text style={ts.bullet}>• A 20% platform commission is applied to all gifting transactions at the point of payout to a creator.</Text>
            <Text style={ts.bullet}>• The minimum withdrawal threshold is 1,000 Points (net payout: 80 ETB). Payouts are processed via telebirr.</Text>
            <Text style={ts.subSectionTitle}>5.3 Content Boosting (Coin-Powered)</Text>
            <TermsTable
              headers={['Boost Type', 'Cost', 'Effect', 'Leaderboard Impact']}
              flex={[1, 0.8, 1.4, 1.5]}
              rows={[
                ['Standard Boost', '100 Coins', "Featured in 'Trending' for 1 hour.", 'Boosted views do NOT count toward organic score.'],
                ['Premium Boost', '500 Coins', "Top of 'For You' feed for 6 hours.", 'Boosted views do NOT count toward organic score.'],
                ['Viral Boost', '1,000 Coins', '5,000 guaranteed impressions.', 'Boosted views do NOT count toward organic score.'],
              ]}
            />

            {/* 6 */}
            <Text style={ts.sectionTitle}>6. Content and Upload Rules</Text>
            <Text style={ts.subSectionTitle}>6.1 Upload Limits</Text>
            <TermsTable
              headers={['User Type', 'Video Limit', 'Access']}
              flex={[1.2, 0.9, 1.5]}
              rows={[
                ['Standard subscriber', '15 – 60 seconds', 'Available to all active subscribers.'],
                ['Coin buyer (On-Demand / Premium)', 'Up to 90–120 seconds', 'Unlocked by purchasing coins or on-demand packs.'],
              ]}
            />
            <Text style={ts.subSectionTitle}>6.2 User-Generated Content (UGC)</Text>
            <Text style={ts.bullet}>• By uploading content to FlipStar, you grant Ethio Telecom and SkykinTechnologies PLC a non-exclusive, royalty-free, worldwide licence to host, store, reproduce, and promote your content within and in connection with the FlipStar platform.</Text>
            <Text style={ts.bullet}>• By participating in the service, you agree that your data (including name, initials, photos, and video images) may be used by Ethio Telecom for promotional and advertising purposes at no charge and without requiring prior individual consent.</Text>
            <Text style={ts.bullet}>• All content uploaded for Weekly reward campaigns and above must pass AI and/or manual moderation for brand safety before becoming eligible for rewards.</Text>
            <Text style={ts.bullet}>• All personal metadata (GPS location, device information) is automatically removed from all uploaded Flips before storage and publication.</Text>
            <Text style={ts.subSectionTitle}>6.3 Prohibited Content and Behaviour</Text>
            <Text style={ts.bullet}>• Users must not upload content that is unlawful, harmful, threatening, abusive, defamatory, or otherwise objectionable under Ethiopian law.</Text>
            <Text style={ts.bullet}>• Botting, automated engagement, self-gifting, vote manipulation, or any attempt to artificially inflate scores or leaderboard rankings is strictly prohibited and results in immediate permanent account ban.</Text>
            <Text style={ts.bullet}>• A single user may contribute a maximum of 5,000 Score Points (equivalent to 500 Coins) per day to any one specific creator ('Voting Cap'). This rule exists to prevent pay-to-win manipulation.</Text>
            <Text style={ts.bullet}>• Ethio Telecom and SkykinTechnologies PLC reserve the right to disqualify any participant found to have breached these Terms and to ban any user who engages in inappropriate behaviour.</Text>

            {/* 7 */}
            <Text style={ts.sectionTitle}>7. Competitions and Rewards</Text>
            <Text style={ts.subSectionTitle}>7.1 The Engagement Score Formula</Text>
            <Text style={ts.para}>Your position on the competition leaderboard is determined by your Engagement Index, calculated as follows:</Text>
            <View style={ts.formulaBox}>
              <Text style={ts.formulaText}>Score = (Likes × 1) + (Comments × 2) + (Shares × 5) + (Gift/Vote Points × 10)</Text>
            </View>
            <Text style={ts.para}>The user with the highest Engagement Score at the end of each competition period is declared the winner for that tier.</Text>
            <Text style={ts.subSectionTitle}>7.2 Competition Tiers and Prize Structure</Text>
            <TermsTable
              headers={['Tier', 'Winners', 'Prize', 'Delivery']}
              flex={[1.3, 0.6, 1.1, 1.5]}
              rows={[
                ['Daily Sprint', '50', '1 GB Daily Data', 'Credited to telebirr/account within 24 hours.'],
                ['Weekly Battle', '10', '1,000 ETB', 'Via telebirr within 10 days.'],
                ['Monthly Star', '5', '10,000 ETB', 'Via telebirr within 10 days.'],
                ['Grand Final — 1st (Legend)', '1', '500,000 ETB', 'Within 20 days. Winner contacted by phone.'],
                ['Grand Final — 2nd (Icon)', '1', '300,000 ETB', 'Within 20 days. Winner contacted by phone.'],
                ['Grand Final — 3rd (Spark)', '1', '200,000 ETB', 'Within 20 days. Winner contacted by phone.'],
              ]}
            />
            <Text style={ts.subSectionTitle}>7.3 Winner Cooldown Rules</Text>
            <Text style={ts.bullet}>• Winners of a specific tier are ineligible to win that same tier again for 30 days from the date of winning.</Text>
            <Text style={ts.bullet}>• During the 30-day cooldown, winners remain fully eligible to compete for all other tiers.</Text>
            <Text style={ts.bullet}>• Eligibility for the same tier is automatically restored after 30 days.</Text>
            <Text style={ts.bullet}>• A single user may win Daily, Weekly, and Monthly rewards within the same 30-day period, provided each win is in a different tier.</Text>
            <Text style={ts.subSectionTitle}>7.4 Prize Redemption</Text>
            <Text style={ts.bullet}>• Cash prizes (ETB) will be sent via telebirr to the mobile number registered with the winning account.</Text>
            <Text style={ts.bullet}>• Daily Data prizes are credited directly to the winner's Ethio Telecom account within 24 hours.</Text>
            <Text style={ts.bullet}>• Grand Final and non-cash prize winners will be contacted by Ethio Telecom or SkykinTechnologies PLC representatives via the registered phone number.</Text>
            <Text style={ts.bullet}>• All winners must present a valid identification document (National ID card or valid passport) to receive non-cash prizes.</Text>
            <Text style={ts.bullet}>• Prizes may be received by an authorised representative upon written proxy confirmation from the winner, accompanied by valid identification of both parties.</Text>
            <Text style={ts.bullet}>• Unclaimed prizes expire after 30 days from the date of notification. Expired prizes are awarded to the next eligible runner-up.</Text>
            <View style={ts.infoBox}>
              <Text style={ts.infoText}>ⓘ Grand Final Winner Note: If a winner of the Grand Final is found to have won a Grand Final prize previously using the same mobile number, the prize will be awarded to the next eligible participant who has not yet received a Grand Final prize.</Text>
            </View>

            {/* 8 */}
            <Text style={ts.sectionTitle}>8. Eligibility</Text>
            <Text style={ts.subSectionTitle}>8.1 Eligible Participants</Text>
            <Text style={ts.bullet}>• Individuals aged 13 years and above.</Text>
            <Text style={ts.bullet}>• For prize collection: individuals aged 18 and above; minors under 18 must be accompanied by a parent or legal guardian to claim prizes.</Text>
            <Text style={ts.bullet}>• Legal entities with duly authorised representatives.</Text>
            <Text style={ts.bullet}>• All active Ethio Telecom prepaid, postpaid, and hybrid mobile customers.</Text>
            <Text style={ts.subSectionTitle}>8.2 Non-Eligible Participants</Text>
            <Text style={ts.bullet}>• Employees of Ethio Telecom and all directly associated partner organisations are not eligible to participate in prize competitions.</Text>
            <Text style={ts.bullet}>• Any user found to have used automated tools (bots), multiple accounts, or any form of manipulation to influence competition results will be immediately and permanently disqualified and banned from the service.</Text>

            {/* 9 */}
            <Text style={ts.sectionTitle}>9. Data Usage Fees</Text>
            <Text style={ts.bullet}>• Accessing FlipStar via https://flipstar.et or the mobile app uses your regular Ethio Telecom data plan.</Text>
            <Text style={ts.bullet}>• You are solely responsible for any internet access or data charges incurred from your mobile carrier in connection with using the FlipStar service.</Text>
            <Text style={ts.bullet}>• Ethio Telecom is not responsible for data charges incurred as a result of using the FlipStar service.</Text>

            {/* 10 */}
            <Text style={ts.sectionTitle}>10. Service Updates</Text>
            <Text style={ts.bullet}>• For FlipStar to function properly, certain components may require updates from time to time. By accepting these Terms, you consent to the automatic installation of such updates.</Text>
            <Text style={ts.bullet}>• During system updates, ongoing transactions, digital coins, earned points, and accumulated data remain unaffected.</Text>
            <Text style={ts.bullet}>• Ethio Telecom reserves the right to temporarily suspend the service for operational reasons. The service will be restored as soon as reasonably possible following any temporary suspension.</Text>

            {/* 11 */}
            <Text style={ts.sectionTitle}>11. Inactivity Policy</Text>
            <Text style={ts.bullet}>• Points not withdrawn or converted within 180 days of account inactivity are permanently forfeited.</Text>
            <Text style={ts.bullet}>• Coins and tickets remain valid for up to 30 days for unsubscribed users and are restored upon re-subscription within that period, provided they have not expired.</Text>
            <Text style={ts.bullet}>• Users are encouraged to log in daily to maintain activity and protect their earned assets.</Text>

            {/* 12 */}
            <Text style={ts.sectionTitle}>12. Content Moderation</Text>
            <Text style={ts.bullet}>• FlipStar employs a hybrid AI and manual moderation system to review content for brand safety, legal compliance, and community standards.</Text>
            <Text style={ts.bullet}>• All content submitted for Weekly competitions and above must successfully pass moderation review before becoming eligible for rewards.</Text>
            <Text style={ts.bullet}>• Ethio Telecom and SkykinTechnologies PLC reserve the right to remove any content that violates these Terms or applicable Ethiopian law without prior notice.</Text>

            {/* 13 */}
            <Text style={ts.sectionTitle}>13. Acceptance of Terms and Modifications</Text>
            <Text style={ts.bullet}>• By subscribing to or using the FlipStar service, you confirm that you have read, understood, and agreed to these Terms and Conditions.</Text>
            <Text style={ts.bullet}>• Ethio Telecom reserves the right to cancel, amend, or modify these Terms and the service at any time. Any changes will be published at https://flipstar.et.</Text>
            <Text style={ts.bullet}>• By continuing to access or use the service after revised Terms become effective, you agree to be bound by the revised Terms. If you do not agree to the new Terms, you must stop using the service.</Text>
            <Text style={ts.bullet}>• These Terms shall remain in full force from the launch of the service until it is officially terminated, excluding temporary suspensions for operational reasons.</Text>

            {/* 14 */}
            <Text style={ts.sectionTitle}>14. Participants and Disqualification</Text>
            <Text style={ts.bullet}>• Ethio Telecom reserves the right to disqualify any participant who appears to have breached any provision of these Terms.</Text>
            <Text style={ts.bullet}>• Customers participating in the service warrant that all information submitted is true, current, and complete.</Text>
            <Text style={ts.bullet}>• In the event of any dispute regarding these Terms, competition results, or any other matter relating to the service, the decision of Ethio Telecom shall be final.</Text>

            {/* 15 */}
            <Text style={ts.sectionTitle}>15. Limitation of Liability</Text>
            <Text style={ts.bullet}>• Ethio Telecom accepts no responsibility for errors, omissions, interruptions, defects, delays in operation or transmission, or communications failures that are not within its direct control.</Text>
            <Text style={ts.bullet}>• Ethio Telecom is not responsible for problems or technical malfunctions of telephone networks, internet lines, computer systems, servers, or any combination thereof.</Text>
            <Text style={ts.bullet}>• Participants understand and agree that they participate in this service at their own risk and have not been coerced into participation.</Text>
            <Text style={ts.bullet}>• No claim relating to losses or injuries (including special, indirect, and consequential losses) shall be asserted against Ethio Telecom, SkykinTechnologies PLC, their parent companies, affiliates, directors, officers, employees, or agents.</Text>

            {/* 16 */}
            <Text style={ts.sectionTitle}>16. Disclaimer of Warranties</Text>
            <Text style={ts.bullet}>• Ethio Telecom makes no warranty, implied or express, that any part of the FlipStar service will be uninterrupted and error-free.</Text>
            <Text style={ts.bullet}>• The service is provided on an 'as is' basis. Users accept that technical disruptions may occur.</Text>

            {/* 17 */}
            <Text style={ts.sectionTitle}>17. Governing Law</Text>
            <Text style={ts.para}>In the event of any disagreement arising from the use of this service, participants may present their complaint to Ethio Telecom. All disputes shall be resolved in accordance with the laws of the Federal Democratic Republic of Ethiopia (FDRE).</Text>

            {/* 18 */}
            <Text style={ts.sectionTitle}>18. Contact Information</Text>
            <TermsTable
              headers={['Channel', 'Contact Detail']}
              flex={[1, 1.8]}
              rows={[
                ['In-App Support', 'Profile → Help & Support → Contact Us'],
                ['Email', 'support@flipstar.et'],
                ['SMS', '8994'],
                ['Website', 'https://www.ethiotelecom.et/'],
                ['Email (Ethio Telecom)', '994@ethionet.et'],
                ['WhatsApp', '+251 99 400 0000'],
                ['Telegram', 'https://t.me/ethio_telecom'],
              ]}
            />

            <View style={{ height: 40 }} />
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

// ── Main Login Screen ──────────────────────────────────────────────────────
export default function LoginScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { loadUser } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [modal, setModal] = useState(null); // 'forgot-phone' | 'faq' | 'terms'
  const [subscriptionOtpMode, setSubscriptionOtpMode] = useState(false);
  const [subPhone, setSubPhone] = useState('');
  const [subUsername, setSubUsername] = useState('');
  const [subOtp, setSubOtp] = useState('');
  const [subPassword, setSubPassword] = useState('');
  const [showSubPassword, setShowSubPassword] = useState(false);
  const [focusedIdentifier, setFocusedIdentifier] = useState(false);
  const [focusedPwd, setFocusedPwd] = useState(false);
  const [focusedSubPhone, setFocusedSubPhone] = useState(false);
  const [focusedSubUsername, setFocusedSubUsername] = useState(false);
  const [focusedSubOtp, setFocusedSubOtp] = useState(false);
  const [focusedSubPwd, setFocusedSubPwd] = useState(false);
  const [showSubscriptionModal, setShowSubscriptionModal] = useState(false);
  const [showSubscriptionPlans, setShowSubscriptionPlans] = useState(false);
  const [prefillPhone, setPrefillPhone] = useState('');
  const [prefillOtp, setPrefillOtp] = useState('');

  // Check URL params for subscription OTP mode (similar to website)
  useEffect(() => {
    // For mobile, we can check navigation params or AsyncStorage
    // For now, keeping the same logic as website
    setSubscriptionOtpMode(false);
    
    // Check for subscription parameters (could come from deep link)
    // This would be implemented based on how the app handles deep links
    checkForSubscriptionParams();
  }, []);

  const checkForSubscriptionParams = async () => {
    // This would check for deep link parameters like:
    // ?subscription_tp=true&phone=251XXXXXXXXX&otp=XXXXXX
    // For now, we'll keep it simple but the structure is ready
    // In a real implementation, you'd use Linking from react-native
  };

  const handleSubscriptionSuccess = (userData) => {
    setShowSubscriptionModal(false);
    // Navigation to main app would be handled by the AuthContext login function
    // The user is now logged in and registered
  };

  const handleBackToLogin = () => {
    setShowSubscriptionModal(false);
  };

  const handleSubscriptionPlansSuccess = () => {
    setShowSubscriptionPlans(false);
    // After subscription is confirmed, show the registration modal
    // In a real implementation, you would get the phone and OTP from the backend
    // For now, we'll show the registration modal for manual entry
    setShowSubscriptionModal(true);
  };

  const handleLogin = async () => {
    if (!identifier || !password) { setError('Please fill in all fields'); return; }
    
    // Clear any existing auth token before login (prevents interference)
    await api.clearAuth();
    
    setError('');
    setLoading(true);
    try {
      // Use identifier as-is (phone number)
      const phone = identifier.trim();
      console.log('🔐 Attempting login with phone:', phone);
      
      // Use login-with-phone endpoint (same as website)
      const data = await api.request('/auth/login-with-phone/', {
        method: 'POST',
        body: JSON.stringify({ 
          phone: phone,
          password: password 
        }),
      });
      
      console.log('✅ Login successful:', {
        userId: data.user?.id,
        username: data.user?.username,
        token: data.token ? data.token.substring(0, 10) + '...' : 'NONE'
      });
      
      // Set the auth token
      if (data.token) {
        await api.setAuthToken(data.token);
      }
      
      // Load user data from API using the token
      await loadUser();
      
      console.log('✅ Login successful with phone + PIN');
    } catch (error) {
      console.log('Login error:', error);
      const errMsg = error?.message || '';
      if (errMsg.includes('Invalid password') || errMsg.includes('Invalid credentials') || errMsg.includes('401')) {
        Alert.alert('Invalid PIN', 'The PIN you entered is incorrect. Please try again or use "Forgot PIN" to reset it.');
      } else if (errMsg.includes('not found') || errMsg.includes('No account')) {
        Alert.alert('Account Not Found', 'No account found with this phone number. Please check and try again.');
      } else {
        Alert.alert('Login Failed', 'Unable to login. Please check your phone number and PIN.');
      }
      setError('');
    } finally {
      setLoading(false);
    }
  };

  const handleSubscriptionOtpLogin = async () => {
    if (!subPhone || !subUsername || !subOtp || !subPassword) {
      setError('Please fill in all fields');
      return;
    }
    if (!/^\d{6}$/.test(subPassword)) {
      setError('Password must be exactly 6 digits');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const res = await api.request('/auth/login-with-subscription-otp/', {
        method: 'POST',
        body: JSON.stringify({
          phone: subPhone,
          username: subUsername,
          otp: subOtp,
          password: subPassword
        }),
      });
      await api.setAuthToken(res.token);
      await login(subUsername, subPassword);
    } catch (e) {
      setError(e?.response?.data?.error || 'Invalid OTP or subscription not found');
    } finally { setLoading(false); }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <StatusBar barStyle="light-content" backgroundColor="#000000" />
      {modal === 'forgot-phone' && <ForgotPasswordPhone onClose={() => setModal(null)} />}
      {modal === 'faq' && <FaqModal onClose={() => setModal(null)} />}
      {modal === 'terms' && <TermsModal onClose={() => setModal(null)} />}
      
      {/* Subscription Plans Modal */}
      <SubscriptionPlansModal
        visible={showSubscriptionPlans}
        onClose={() => setShowSubscriptionPlans(false)}
        onSuccess={handleSubscriptionPlansSuccess}
        user={null}
      />

      {/* Subscription Register Modal */}
      <SubscriptionRegisterModal
        visible={showSubscriptionModal}
        prefillPhone={prefillPhone}
        prefillOtp={prefillOtp}
        onSuccess={handleSubscriptionSuccess}
        onBackToLogin={handleBackToLogin}
      />

      <ScrollView style={s.container} contentContainerStyle={[s.scroll, { paddingTop: insets.top + 16 }]} showsVerticalScrollIndicator={false}>
        {/* Premium Co-Brand Header with Improved Diagonal */}
        <View style={s.headerContainer}>
          {/* LEFT WHITE SECTION */}
          <View style={s.leftSection}>
            <Image
              source={require('../../../assets/images/ethio-logo.png')}
              style={s.ethioLogo}
              resizeMode="contain"
            />
          </View>

          {/* RIGHT BLACK SECTION */}
          <LinearGradient
            colors={['#0D0D0D', '#1A1A1A']}
            style={s.rightSection}
          >
            <Image
              source={require('../../../assets/images/flipstar-logo.png')}
              style={s.flipstarLogo}
              resizeMode="contain"
            />
          </LinearGradient>

          {/* WHITE BACKGROUND AND GOLD DIAGONAL LINE */}
          <Svg
            height="100%"
            width="100"
            style={s.diagonalContainer}
          >
            {/* White path covering left side of diagonal */}
            <Path
              d="M 0,0 L 55,0 L 20,90 L 0,90 Z"
              fill="#FFFFFF"
            />
            {/* Gold diagonal line */}
            <Line
              x1="20"
              y1="90"
              x2="55"
              y2="0"
              stroke="#D4AF37"
              strokeWidth="12.5"
              strokeLinecap="round"
            />
          </Svg>
        </View>

        {/* Main Content - Website Style */}
        <View style={s.mainContent}>
          <View style={s.header}>
            <Text style={s.title}>Welcome!</Text>
            <Text style={s.subtitle}>Log in to continue to FLIPSTAR</Text>
          </View>

          {/* Error */}
          {!!error && <View style={s.errorBox}><Text style={s.errorText}>⚠️ {error}</Text></View>}

          {/* Phone Number Only */}
          <View style={s.inputGroup}>
            <Text style={s.label}>Phone Number</Text>
            <View style={[s.inputRow, focusedIdentifier && s.inputRowFocused]}>
              <Ionicons name="call-outline" size={17} color={GOLD} style={s.inputIcon} />
              <TextInput
                style={[s.textInput, { flex: 1 }]}
                placeholder="09XXXXXXXX or +2519XXXXXXXXX"
                placeholderTextColor="#555"
                value={identifier}
                onChangeText={setIdentifier}
                autoCapitalize="none"
                keyboardType="phone-pad"
                onFocus={() => setFocusedIdentifier(true)}
                onBlur={() => setFocusedIdentifier(false)}
              />
            </View>
          </View>

          {/* PIN */}
          <View style={s.inputGroup}>
            <Text style={s.label}>PIN</Text>
            <View style={[s.inputRow, focusedPwd && s.inputRowFocused]}>
              <Ionicons name="lock-closed-outline" size={17} color={GOLD} style={s.inputIcon} />
              <TextInput
                style={[s.textInput, { flex: 1 }]}
                placeholder="••••••"
                placeholderTextColor="#555"
                value={password}
                onChangeText={t => setPassword(t.replace(/\D/g, '').slice(0, 6))}
                secureTextEntry={!showPwd}
                keyboardType="number-pad"
                maxLength={6}
                onFocus={() => setFocusedPwd(true)}
                onBlur={() => setFocusedPwd(false)}
              />
              <TouchableOpacity onPress={() => setShowPwd(v => !v)} style={{ padding: 4 }}>
                <Ionicons name={showPwd ? 'eye-off-outline' : 'eye-outline'} size={17} color={GOLD} />
              </TouchableOpacity>
            </View>
          </View>

          {/* Forgot */}
          <TouchableOpacity style={s.forgotRow} onPress={() => setModal('forgot-phone')}>
            <Text style={s.forgotText}>Forgot PIN?</Text>
          </TouchableOpacity>

          {/* Login Button */}
          <TouchableOpacity style={[s.loginBtn, loading && s.loginBtnDisabled]} onPress={handleLogin} disabled={loading}>
            {loading ? <ActivityIndicator color="#000" /> : <Text style={s.loginBtnText}>Log In</Text>}
          </TouchableOpacity>

          {/* Subscribe Option */}
          <View style={s.registerSection}>
            <Text style={s.registerText}>New to FlipStar? </Text>
            <TouchableOpacity onPress={() => setShowSubscriptionPlans(true)}>
              <Text style={s.registerLink}>Subscribe</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Footer */}
        <View style={s.footer}>
          <TouchableOpacity onPress={() => setModal('faq')}><Text style={s.footerLink}>FAQ</Text></TouchableOpacity>
          <Text style={s.footerSep}>|</Text>
          <TouchableOpacity onPress={() => setModal('terms')}><Text style={s.footerLink}>Terms & Conditions</Text></TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  scroll: { padding: 16, paddingBottom: 40 },
  headerContainer: {
    height: 90,
    flexDirection: 'row',
    overflow: 'hidden',
    borderRadius: 18,
    marginHorizontal: 0,
    marginTop: 15,
    marginBottom: 80,
    position: 'relative',
  },
  leftSection: {
    width: '45%',
    backgroundColor: '#FFFFFF',
    justifyContent: 'center',
    paddingLeft: 10,
    zIndex: 2,
  },
  rightSection: {
    width: '55%',
    justifyContent: 'center',
    alignItems: 'flex-end',
    paddingRight: 10,
  },
  diagonalContainer: {
    position: 'absolute',
    left: '38%',
    top: 0,
    bottom: 0,
    zIndex: 3,
  },
  ethioLogo: {
    width: 130,
    height: 45,
  },
  flipstarLogo: {
    width: 180,
    height: 70,
  },
  mainContent: {
    flex: 1,
  },
  header: {
    alignItems: 'center',
    marginBottom: 32,
  },
  title: {
    fontSize: 32,
    fontWeight: '900',
    color: GOLD,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: '#999',
    textAlign: 'center',
  },
  errorBox: { 
    backgroundColor: '#2D1010', 
    borderWidth: 1, 
    borderColor: '#EF4444', 
    borderRadius: 8, 
    padding: 10, 
    marginBottom: 16 
  },
  errorText: { 
    color: '#EF4444', 
    fontSize: 13, 
    fontWeight: '600' 
  },
  inputGroup: {
    marginBottom: 16,
  },
  label: { 
    fontSize: 13, 
    fontWeight: '700', 
    color: '#999', 
    marginBottom: 8, 
    letterSpacing: 0.3 
  },
  inputRow: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    backgroundColor: '#1A1A1A', 
    borderRadius: 12, 
    borderWidth: 1, 
    borderColor: '#333', 
    paddingHorizontal: 14, 
    height: 52 
  },
  inputRowFocused: { 
    borderColor: GOLD,
    backgroundColor: '#1A1A1A',
  },
  inputIcon: { 
    marginRight: 10 
  },
  textInput: { 
    flex: 1, 
    fontSize: 15, 
    color: '#fff' 
  },
  forgotRow: { 
    alignItems: 'flex-end', 
    marginBottom: 24, 
    marginTop: -8 
  },
  forgotText: { 
    color: GOLD, 
    fontSize: 13, 
    fontWeight: '700' 
  },
  loginBtn: { 
    backgroundColor: GOLD, 
    borderRadius: 12, 
    height: 52, 
    justifyContent: 'center', 
    alignItems: 'center', 
    marginBottom: 24 
  },
  loginBtnDisabled: { 
    backgroundColor: '#3A3A3A' 
  },
  loginBtnText: { 
    color: '#000', 
    fontSize: 16, 
    fontWeight: '800' 
  },
  registerSection: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginBottom: 8,
  },
  registerText: {
    fontSize: 13,
    color: '#999',
  },
  registerLink: {
    fontSize: 13,
    color: GOLD,
    fontWeight: '700',
  },
  footer: { 
    flexDirection: 'row', 
    justifyContent: 'center', 
    alignItems: 'center', 
    gap: 24, 
    paddingTop: 20,
    paddingBottom: 40,
    marginTop: 20,
  },
  footerLink: { 
    color: GOLD, 
    fontSize: 15, 
    fontWeight: '800' 
  },
  footerSep: { 
    color: '#666', 
    fontSize: 15,
    fontWeight: '600'
  },
  // Modal styles
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.85)', justifyContent: 'flex-end' },
  modalSheet: { backgroundColor: '#1A1A1A', borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: 24, paddingBottom: 40, maxHeight: '88%' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  modalTitle: { fontSize: 20, fontWeight: 900, color: GOLD },
  modalDesc: { fontSize: 13, color: '#999', marginBottom: 16, lineHeight: 20 },
  input: { backgroundColor: '#0D0D0D', borderRadius: 10, borderWidth: 1.5, borderColor: '#333', paddingHorizontal: 14, paddingVertical: 12, color: '#fff', fontSize: 15, marginBottom: 12 },
  modalBtn: { backgroundColor: GOLD, borderRadius: 10, paddingVertical: 13, marginTop: 8, marginBottom: 12 },
  modalBtnText: { color: '#000', fontSize: 15, fontWeight: '800', textAlign: 'center' },
  modalBtnDisabled: { backgroundColor: '#3A3A3A' },
  modalBtnTextDisabled: { color: '#666' },
  modalFooter: { flexDirection: 'row', justifyContent: 'center', marginTop: 16 },
  modalFooterText: { color: GOLD, fontSize: 13, fontWeight: '600' },
  termsText: { fontSize: 12, color: '#999', lineHeight: 20 },
  position: { position: 'relative' },
  // FAQ styles
  faqItem: { marginBottom: 12, borderBottomWidth: 1, borderBottomColor: '#333', paddingBottom: 12 },
  faqQ: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 8 },
  faqQText: { fontSize: 15, fontWeight: '700', color: '#fff', flex: 1, marginRight: 8 },
  faqA: { fontSize: 14, color: '#ccc', lineHeight: 22, marginTop: 8, paddingLeft: 4 },
});
