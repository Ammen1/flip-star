import { useState } from "react";
import { X, ChevronLeft, ChevronUp, ChevronDown, Eye, EyeOff, Loader, Lock, Mail, User } from "lucide-react";
import { useTheme } from "../contexts/ThemeContext";
import api from "../api";
import { ForgotPasswordPhone } from "./ForgotPasswordPhone";

const GOLD = "linear-gradient(to bottom, #8fc441 0%, #b5dd8f 50%, #6ba835 100%)";

const FAQ_ITEMS = [
  { q: "What is FlipStar?", a: "FlipStar is a premium, subscription-based gamified social media platform by Ethio Telecom and Skykin Technologies PLC. Upload short videos and photos ('Flips'), compete in campaigns, earn coins, and participate in a creator economy powered by telebirr." },
  { q: "Who can use FlipStar?", a: "All active Ethio Telecom prepaid, postpaid, and hybrid mobile customers with a smartphone (Android, iOS) or web browser. Users must be at least 13 years old. For claiming prizes, users must be 18 or older." },
  { q: "What devices and platforms does FlipStar support?", a: "Android App: Available on Google Play Store (search: FlipStar). iOS App: Available on Apple App Store (search: FlipStar). Web: Visit https://flipstar.et in any modern browser." },
  { q: "Is FlipStar available to all Ethio Telecom customers?", a: "Yes. All active prepaid, postpaid, and hybrid Ethio Telecom mobile customers can subscribe and use the service. The subscriber's number must be in 'Active' status at the time of subscription." },
  { q: "How do I subscribe to FlipStar?", a: "Via SMS: Send 'OK' to the FlipStar shortcode. Via App/Web: Download the app or visit https://flipstar.et, select 'Sign Up', enter your full name and mobile number, then enter the confirmation code sent to your number." },
  { q: "What subscription plans are available?", a: "Flip Daily: 3 ETB/24hrs • Flip Weekly: 20 ETB/7days • Flip Monthly: 70 ETB/30days • Flip Yearly: 600 ETB/365days • Flip On-Demand: 10 ETB for 100 Coins (one-time purchase)." },
  { q: "Is there a free trial?", a: "Yes. New subscribers receive a 1-day (24-hour) free trial on their first subscription. Re-subscribers who previously used the trial are not eligible for another." },
  { q: "How am I charged?", a: "Prepaid: fee deducted from airtime balance. Postpaid: fee added to monthly bill. Hybrid: charged from your default account. A maximum of one charge applies per 24-hour cycle. Failed charges are retried automatically if you recharge the same day." },
  { q: "How do I unsubscribe?", a: "Send 'STOP' to the FlipStar shortcode, or go to Account Settings in the app and select Unsubscribe. Your request is processed immediately and you will receive a confirmation SMS." },
  { q: "What happens to my coins and progress if I unsubscribe?", a: "Your coins and digital assets remain valid for 30 days after unsubscription. Re-subscribing within 30 days restores your unexpired coins and progress. Assets not recovered within 30 days will expire." },
  { q: "What are coins and how do I earn them?", a: "Coins are FlipStar's digital currency. Earn them through: Daily login bonus (3 coins/day), Weekly loyalty bonus (50 coins for 7-day streak), or Purchase (1 ETB = 10 Coins via telebirr/Airtime)." },
  { q: "What can I do with coins?", a: "Gift creators, boost your content visibility, unlock extended video uploads (up to 90-120 seconds), level up, and unlock premium features." },
  { q: "Can I cash out my coins?", a: "Bonus coins (from login/loyalty) cannot be cashed out. However, Points earned by creators from gifts can be cashed out via telebirr. Minimum: 1,000 Points (80 ETB after 20% commission)." },
  { q: "What is the platform commission?", a: "A 20% commission applies to all gifting transaction payouts. For example: if a creator earns 1,000 Points, 200 Points (20%) are retained as platform commission, and the creator receives 800 Points (80 ETB) via telebirr." },
  { q: "Can I convert my Points back into Coins?", a: "Yes. The swap rate is 1 Point = 1 Coin. You can use earned Points to purchase more Coins for in-app spending instead of cashing out." },
  { q: "What is a Flip and how do I upload one?", a: "A Flip is a short video (15–120 seconds) or photo you upload to the platform. Tap the '+' button, select or record your content, add a caption and hashtags, optionally link it to a campaign, and tap 'Post'." },
  { q: "How long can my videos be?", a: "Standard subscribers: 15 to 60 seconds. Coin buyers (On-Demand / premium): up to 90–120 seconds." },
  { q: "What are the competition prizes?", a: "Daily Sprint (50 winners): 1GB data • Weekly Battle (10 winners): 1,000 ETB • Monthly Star (5 winners): 10,000 ETB • Grand Final: 1st-500,000 ETB, 2nd-300,000 ETB, 3rd-200,000 ETB." },
  { q: "How is my competition score calculated?", a: "Score = (Likes × 1) + (Comments × 2) + (Shares × 5) + (Gift/Vote Points × 10). The highest Engagement Score wins each tier." },
  { q: "Can I win multiple prizes?", a: "Yes, with rules. After winning a tier, you're ineligible for that same tier for 30 days. You can still win other tiers during the cooldown. Eligibility restores after 30 days." },
  { q: "How do I claim my prize?", a: "Cash prizes (ETB): sent automatically via telebirr. Daily Data prizes: credited to your Ethio Telecom account within 24 hours. Grand Final prizes: our team will contact you — you must present a valid National ID or passport. All prizes must be claimed within 30 days of notification." },
  { q: "Is there a daily voting limit for one creator?", a: "Yes. A single user can contribute a maximum of 5,000 Score Points (equivalent to 500 Coins) per day to any one specific creator. This Voting Cap prevents pay-to-win behaviour and protects competition integrity." },
  { q: "Do boosted views count toward my leaderboard score?", a: "No. Views and impressions from paid content boosts (Standard, Premium, or Viral Boost) do not count toward your organic Engagement Score. Only genuine, unboosted engagement contributes to your score." },
  { q: "Are there internet data charges for using FlipStar?", a: "Yes. Accessing FlipStar via the app or web portal at https://flipstar.et uses your regular Ethio Telecom data plan. You are responsible for any data charges incurred." },
  { q: "Is my personal data safe?", a: "Yes. FlipStar is hosted on Ethio Telecom InfraCloud within Ethiopia. Your phone number is encrypted and never displayed publicly. All personal metadata is removed from uploads." },
  { q: "Can Ethio Telecom change the Terms or cancel the service?", a: "Yes. Ethio Telecom reserves the right to modify, suspend, or terminate the FlipStar service at any time in accordance with Ethiopian laws. Changes will be published at https://flipstar.et. Continued use after changes take effect constitutes acceptance." },
  { q: "How do I contact support?", a: "In-App: Profile → Help & Support • Email: support@flipstar.et • SMS: 8994 • WhatsApp: +251 99 400 0000 • Telegram: t.me/ethio_telecom • Web: ethiotelecom.et" },
];

// ── shared bottom-sheet overlay (used by FAQ) ───────────────────────────────
function Overlay({ onClose, children }) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", zIndex: 9999, display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: "#111", borderRadius: "18px 18px 0 0", width: "100%", maxWidth: 520, maxHeight: "88vh", overflowY: "auto", padding: "24px 20px 40px" }}>
        {children}
      </div>
    </div>
  );
}

// ── FAQ accordion modal ─────────────────────────────────────────────────────
function FaqModal({ onClose }) {
  const [open, setOpen] = useState(null);
  return (
    <Overlay onClose={onClose}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div style={{ fontSize: 20, fontWeight: 900, color: "#8fc441" }}>FAQ</div>
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#8fc441" }}><X size={22} /></button>
      </div>
      {FAQ_ITEMS.map((item, i) => (
        <div key={i} style={{ borderBottom: "1px solid #262626", marginBottom: 2 }}>
          <button onClick={() => setOpen(open === i ? null : i)}
            style={{ width: "100%", background: "none", border: "none", cursor: "pointer", padding: "14px 0", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: "#fff", textAlign: "left" }}>{item.q}</span>
            {open === i ? <ChevronUp size={16} color="#8fc441" style={{ flexShrink: 0 }} /> : <ChevronDown size={16} color="#8fc441" style={{ flexShrink: 0 }} />}
          </button>
          {open === i && <div style={{ fontSize: 13, color: "#ccc", paddingBottom: 14, lineHeight: 1.6 }}>{item.a}</div>}
        </div>
      ))}
    </Overlay>
  );
}

// ── Terms table helper ──────────────────────────────────────────────────────
function TTable({ headers, rows }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 14, fontSize: 11 }}>
      <thead>
        <tr style={{ background: "#1A1A1A" }}>
          {headers.map((h, i) => (
            <th key={i} style={{ padding: "7px 8px", color: "#8fc441", fontWeight: 700, textAlign: "left", border: "1px solid #333", lineHeight: 1.4 }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, ri) => (
          <tr key={ri} style={{ background: ri % 2 === 1 ? "#111" : "transparent" }}>
            {row.map((cell, ci) => (
              <td key={ci} style={{ padding: "6px 8px", color: "#ccc", border: "1px solid #222", lineHeight: 1.5, verticalAlign: "top" }}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Full-screen Terms & Conditions modal ────────────────────────────────────
function TermsModal({ onClose }) {
  const sec  = { fontSize: 14, fontWeight: 800, color: "#8fc441", marginTop: 20, marginBottom: 8 };
  const sub  = { fontSize: 13, fontWeight: 700, color: "#ddd", marginTop: 12, marginBottom: 6 };
  const para = { fontSize: 12, color: "#ccc", lineHeight: 1.7, marginBottom: 8 };
  const bul  = { fontSize: 12, color: "#bbb", lineHeight: 1.7, marginBottom: 4, paddingLeft: 8 };
  const info = { background: "#1A1A2E", borderLeft: "3px solid #3B82F6", padding: "10px 12px", borderRadius: 6, marginBottom: 12, fontSize: 12, color: "#aaa", lineHeight: 1.6 };
  const form = { background: "#0D1A2B", border: "1px solid #3B82F6", padding: 14, borderRadius: 8, marginBottom: 10, fontSize: 13, color: "#60A5FA", fontWeight: 600, textAlign: "center" };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.97)", zIndex: 9999, overflowY: "auto" }}>
      <div style={{ background: "#111", minHeight: "100vh", width: "100%", maxWidth: 640, margin: "0 auto", padding: "48px 24px 60px" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div style={{ fontSize: 22, fontWeight: 900, color: "#8fc441" }}>Terms &amp; Conditions</div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#8fc441" }}><X size={24} /></button>
        </div>

        {/* Preamble */}
        <p style={para}>Please read these Terms and Conditions ("Terms") carefully before using the FlipStar service ("FlipStar", "the Service") provided by Ethio Telecom and SkykinTechnologies PLC ("the Providers"). These Terms apply to all visitors, users, and others who access or use the Service via the FlipStar mobile application (Android and iOS) or web portal at https://flipstar.et.</p>
        <p style={para}>By subscribing, downloading, installing, or otherwise accessing FlipStar, you acknowledge that you have read, understood, and agree to be bound by these Terms. If you do not agree, do not use the Service.</p>

        {/* 1 */}
        <div style={sec}>1. Introduction</div>
        <p style={para}>FlipStar is a premium, subscription-based gamified social media platform developed for Ethio Telecom customers. The platform enables users to create, share, and discover short-form videos and photos ('Flips'), participate in competitive campaigns, earn rewards, and engage in a digital creator economy powered by the telebirr wallet.</p>
        <p style={para}>FlipStar is accessible via:</p>
        <p style={bul}>• Web Portal: https://flipstar.et</p>
        <p style={bul}>• Android App: Available on Google Play Store (search: FlipStar)</p>
        <p style={bul}>• iOS App: Available on Apple App Store (search: FlipStar)</p>

        {/* 2 */}
        <div style={sec}>2. Service Overview</div>
        <p style={bul}>• FlipStar is available to all active Ethio Telecom prepaid, postpaid, and hybrid mobile customers with a smartphone device (Android, iOS, or any HTML5-capable browser for web access).</p>
        <p style={bul}>• The Service allows users to upload short-form videos (15–120 seconds depending on user tier) and photos, interact with content, participate in daily, weekly, monthly, and grand prize competitions, and earn and spend digital coins.</p>
        <p style={bul}>• To subscribe via SMS: send 'OK' to the FlipStar shortcode. To unsubscribe: send 'STOP' to the same shortcode.</p>
        <p style={bul}>• To subscribe via app or web: download the FlipStar app or visit https://flipstar.et, select Sign Up, and follow the on-screen registration flow.</p>

        {/* 3 */}
        <div style={sec}>3. Subscription and Billing</div>
        <div style={sub}>3.1 Subscription Plans</div>
        <TTable
          headers={["Plan", "Price", "Billing Cycle", "Notes"]}
          rows={[
            ["Flip Daily", "3 ETB", "Every 24 hrs", "Charged daily. Auto-renewed while active."],
            ["Flip Weekly", "20 ETB", "Every 7 days", "Charged weekly. Auto-renewed while active."],
            ["Flip Monthly", "70 ETB", "Every 30 days", "Charged monthly. Auto-renewed while active."],
            ["Flip On-Demand", "10 ETB / 100 Coins", "One-time", "Coins on demand. No recurring charge."],
          ]}
        />
        <div style={sub}>3.2 Eligibility</div>
        <p style={bul}>• All active prepaid, postpaid, and hybrid Ethio Telecom mobile customers are eligible to subscribe.</p>
        <p style={bul}>• The subscriber's service number must be in 'Active' status at the time of subscription.</p>
        <p style={bul}>• After any applicable free trial period, the subscriber must have sufficient balance to continue service.</p>
        <div style={sub}>3.3 Free Trial</div>
        <p style={bul}>• New subscribers receive a 1-day (24-hour) free trial on their first-time subscription.</p>
        <p style={bul}>• The free trial is available for first-time subscribers only. Users who have previously subscribed and cancel are not eligible for a second free trial upon re-subscription.</p>
        <div style={sub}>3.4 Charging Logic</div>
        <p style={bul}>• Prepaid customers: Subscription fees are deducted from the current airtime balance.</p>
        <p style={bul}>• Postpaid customers: Subscription fees are added to the monthly bill.</p>
        <p style={bul}>• Hybrid customers: Fees are charged from the default account.</p>
        <p style={bul}>• A maximum of one subscription charge per 24-hour cycle applies.</p>
        <p style={bul}>• Failed billing attempts will be retried automatically per Ethio Telecom MA time standards, or if the customer recharges their balance within the same day.</p>
        <p style={bul}>• The service will be activated automatically after a successful subscription or payment.</p>
        <div style={sub}>3.5 Auto-Renewal</div>
        <p style={bul}>• FlipStar subscriptions auto-renew at the end of each billing cycle if the subscriber has sufficient balance.</p>
        <p style={bul}>• Upon successful renewal, the subscriber will receive an SMS notification confirming the renewal and extended service period.</p>
        <p style={bul}>• If auto-renewal fails due to insufficient balance, service access may be suspended until the next successful charge or manual resubscription.</p>
        <div style={sub}>3.6 Unsubscription</div>
        <p style={bul}>• To unsubscribe, send 'STOP' to the FlipStar shortcode, or use the unsubscription option within the app or web portal under Account Settings.</p>
        <p style={bul}>• Unsubscription requests are processed immediately.</p>
        <p style={bul}>• A subscriber is considered active until they explicitly unsubscribe. Once cancelled, the user must re-subscribe to regain access to premium features.</p>
        <p style={bul}>• Coins and digital assets earned or purchased prior to unsubscription remain valid for 30 days and are restored upon re-subscription within that period if not expired.</p>
        <div style={info}>ⓘ SMS Notifications: You will receive an automatic SMS for successful subscription, successful unsubscription, and each auto-renewal.</div>

        {/* 4 */}
        <div style={sec}>4. Accounts</div>
        <p style={bul}>• Once you subscribe via SMS or complete registration via the app or web portal, FlipStar will automatically create an account using your Ethio Telecom mobile number as your unique account identifier.</p>
        <p style={bul}>• By accessing the service, you agree to be solely responsible for all activities that occur under your account and mobile number.</p>
        <p style={bul}>• You agree to provide true, current, and complete information during registration and at all times during your use of the service.</p>
        <p style={bul}>• Only one active account per mobile number is permitted.</p>

        {/* 5 */}
        <div style={sec}>5. Digital Coins and the Creator Economy</div>
        <div style={sub}>5.1 Coins Overview</div>
        <p style={para}>FlipStar operates a digital coin system that powers the platform's creator economy. Coins are the platform's internal currency used for content interaction, gifting, and access to premium features.</p>
        <TTable
          headers={["Action", "Rate / Rule"]}
          rows={[
            ["Purchase coins", "1 ETB = 10 Coins via telebirr or Airtime. No commission at purchase."],
            ["On-Demand Pack", "10 ETB = 100 Coins (Flip On-Demand purchase)."],
            ["Daily login bonus", "3 Coins per day for opening the FlipStar app."],
            ["Weekly loyalty bonus", "50 Coins for consistent daily usage for a full week."],
            ["Gift a creator", "Convert Coins into virtual Gifts sent to other users' content."],
            ["Creator earns Points", "1 Coin gifted = 1 Point earned (100% of gift value)."],
            ["Cash out Points", "10 Points = 0.8 ETB (20% platform commission at payout)."],
            ["Re-invest Points", "1 Point = 1 Coin (swap Points back to Coins for in-app spending)."],
            ["Min. cash-out", "1,000 Points (80 ETB net after commission) required for telebirr payout."],
          ]}
        />
        <div style={sub}>5.2 Coin Rules</div>
        <p style={bul}>• Coins purchased via telebirr or Airtime have no expiry when actively used. Coins not used or converted within 30 days of purchase may expire.</p>
        <p style={bul}>• Points not withdrawn or converted within 180 days of account inactivity are forfeited.</p>
        <p style={bul}>• All coin purchases are non-refundable once processed.</p>
        <p style={bul}>• Coins earned via daily bonuses and loyalty rewards may not be cashed out — they may only be spent within the platform (gifting, boosts, etc.).</p>
        <p style={bul}>• A 20% platform commission is applied to all gifting transactions at the point of payout to a creator.</p>
        <p style={bul}>• The minimum withdrawal threshold is 1,000 Points (net payout: 80 ETB). Payouts are processed via telebirr.</p>
        <div style={sub}>5.3 Content Boosting (Coin-Powered)</div>
        <TTable
          headers={["Boost Type", "Cost", "Effect", "Leaderboard Impact"]}
          rows={[
            ["Standard Boost", "100 Coins", "Featured in 'Trending' for 1 hour.", "Boosted views do NOT count toward organic score."],
            ["Premium Boost", "500 Coins", "Top of 'For You' feed for 6 hours.", "Boosted views do NOT count toward organic score."],
            ["Viral Boost", "1,000 Coins", "5,000 guaranteed impressions.", "Boosted views do NOT count toward organic score."],
          ]}
        />

        {/* 6 */}
        <div style={sec}>6. Content and Upload Rules</div>
        <div style={sub}>6.1 Upload Limits</div>
        <TTable
          headers={["User Type", "Video Limit", "Access"]}
          rows={[
            ["Standard subscriber", "15 – 60 seconds", "Available to all active subscribers."],
            ["Coin buyer (On-Demand / Premium)", "Up to 90–120 seconds", "Unlocked by purchasing coins or on-demand packs."],
          ]}
        />
        <div style={sub}>6.2 User-Generated Content (UGC)</div>
        <p style={bul}>• By uploading content to FlipStar, you grant Ethio Telecom and SkykinTechnologies PLC a non-exclusive, royalty-free, worldwide licence to host, store, reproduce, and promote your content within and in connection with the FlipStar platform.</p>
        <p style={bul}>• By participating in the service, you agree that your data (including name, initials, photos, and video images) may be used by Ethio Telecom for promotional and advertising purposes at no charge and without requiring prior individual consent.</p>
        <p style={bul}>• All content uploaded for Weekly reward campaigns and above must pass AI and/or manual moderation for brand safety before becoming eligible for rewards.</p>
        <p style={bul}>• All personal metadata (GPS location, device information) is automatically removed from all uploaded Flips before storage and publication.</p>
        <div style={sub}>6.3 Prohibited Content and Behaviour</div>
        <p style={bul}>• Users must not upload content that is unlawful, harmful, threatening, abusive, defamatory, or otherwise objectionable under Ethiopian law.</p>
        <p style={bul}>• Botting, automated engagement, self-gifting, vote manipulation, or any attempt to artificially inflate scores or leaderboard rankings is strictly prohibited and results in immediate permanent account ban.</p>
        <p style={bul}>• A single user may contribute a maximum of 5,000 Score Points (equivalent to 500 Coins) per day to any one specific creator ('Voting Cap'). This rule exists to prevent pay-to-win manipulation.</p>
        <p style={bul}>• Ethio Telecom and SkykinTechnologies PLC reserve the right to disqualify any participant found to have breached these Terms and to ban any user who engages in inappropriate behaviour.</p>

        {/* 7 */}
        <div style={sec}>7. Competitions and Rewards</div>
        <div style={sub}>7.1 The Engagement Score Formula</div>
        <p style={para}>Your position on the competition leaderboard is determined by your Engagement Index, calculated as follows:</p>
        <div style={form}>Score = (Likes × 1) + (Comments × 2) + (Shares × 5) + (Gift/Vote Points × 10)</div>
        <p style={para}>The user with the highest Engagement Score at the end of each competition period is declared the winner for that tier.</p>
        <div style={sub}>7.2 Competition Tiers and Prize Structure</div>
        <TTable
          headers={["Tier", "Winners", "Prize", "Delivery"]}
          rows={[
            ["Daily Sprint", "50", "1 GB Daily Data", "Credited to telebirr/account within 24 hours."],
            ["Weekly Battle", "10", "1,000 ETB", "Via telebirr within 10 days."],
            ["Monthly Star", "5", "10,000 ETB", "Via telebirr within 10 days."],
            ["Grand Final — 1st (Legend)", "1", "500,000 ETB", "Within 20 days. Winner contacted by phone."],
            ["Grand Final — 2nd (Icon)", "1", "300,000 ETB", "Within 20 days. Winner contacted by phone."],
            ["Grand Final — 3rd (Spark)", "1", "200,000 ETB", "Within 20 days. Winner contacted by phone."],
          ]}
        />
        <div style={sub}>7.3 Winner Cooldown Rules</div>
        <p style={bul}>• Winners of a specific tier are ineligible to win that same tier again for 30 days from the date of winning.</p>
        <p style={bul}>• During the 30-day cooldown, winners remain fully eligible to compete for all other tiers.</p>
        <p style={bul}>• Eligibility for the same tier is automatically restored after 30 days.</p>
        <p style={bul}>• A single user may win Daily, Weekly, and Monthly rewards within the same 30-day period, provided each win is in a different tier.</p>
        <div style={sub}>7.4 Prize Redemption</div>
        <p style={bul}>• Cash prizes (ETB) will be sent via telebirr to the mobile number registered with the winning account.</p>
        <p style={bul}>• Daily Data prizes are credited directly to the winner's Ethio Telecom account within 24 hours.</p>
        <p style={bul}>• Grand Final and non-cash prize winners will be contacted by Ethio Telecom or SkykinTechnologies PLC representatives via the registered phone number.</p>
        <p style={bul}>• All winners must present a valid identification document (National ID card or valid passport) to receive non-cash prizes.</p>
        <p style={bul}>• Prizes may be received by an authorised representative upon written proxy confirmation from the winner, accompanied by valid identification of both parties.</p>
        <p style={bul}>• Unclaimed prizes expire after 30 days from the date of notification. Expired prizes are awarded to the next eligible runner-up.</p>
        <div style={info}>ⓘ Grand Final Winner Note: If a winner of the Grand Final is found to have won a Grand Final prize previously using the same mobile number, the prize will be awarded to the next eligible participant who has not yet received a Grand Final prize.</div>

        {/* 8 */}
        <div style={sec}>8. Eligibility</div>
        <div style={sub}>8.1 Eligible Participants</div>
        <p style={bul}>• Individuals aged 13 years and above.</p>
        <p style={bul}>• For prize collection: individuals aged 18 and above; minors under 18 must be accompanied by a parent or legal guardian to claim prizes.</p>
        <p style={bul}>• Legal entities with duly authorised representatives.</p>
        <p style={bul}>• All active Ethio Telecom prepaid, postpaid, and hybrid mobile customers.</p>
        <div style={sub}>8.2 Non-Eligible Participants</div>
        <p style={bul}>• Employees of Ethio Telecom and all directly associated partner organisations are not eligible to participate in prize competitions.</p>
        <p style={bul}>• Any user found to have used automated tools (bots), multiple accounts, or any form of manipulation to influence competition results will be immediately and permanently disqualified and banned from the service.</p>

        {/* 9 */}
        <div style={sec}>9. Data Usage Fees</div>
        <p style={bul}>• Accessing FlipStar via https://flipstar.et or the mobile app uses your regular Ethio Telecom data plan.</p>
        <p style={bul}>• You are solely responsible for any internet access or data charges incurred from your mobile carrier in connection with using the FlipStar service.</p>
        <p style={bul}>• Ethio Telecom is not responsible for data charges incurred as a result of using the FlipStar service.</p>

        {/* 10 */}
        <div style={sec}>10. Service Updates</div>
        <p style={bul}>• For FlipStar to function properly, certain components may require updates from time to time. By accepting these Terms, you consent to the automatic installation of such updates.</p>
        <p style={bul}>• During system updates, ongoing transactions, digital coins, earned points, and accumulated data remain unaffected.</p>
        <p style={bul}>• Ethio Telecom reserves the right to temporarily suspend the service for operational reasons. The service will be restored as soon as reasonably possible following any temporary suspension.</p>

        {/* 11 */}
        <div style={sec}>11. Inactivity Policy</div>
        <p style={bul}>• Points not withdrawn or converted within 180 days of account inactivity are permanently forfeited.</p>
        <p style={bul}>• Coins and tickets remain valid for up to 30 days for unsubscribed users and are restored upon re-subscription within that period, provided they have not expired.</p>
        <p style={bul}>• Users are encouraged to log in daily to maintain activity and protect their earned assets.</p>

        {/* 12 */}
        <div style={sec}>12. Content Moderation</div>
        <p style={bul}>• FlipStar employs a hybrid AI and manual moderation system to review content for brand safety, legal compliance, and community standards.</p>
        <p style={bul}>• All content submitted for Weekly competitions and above must successfully pass moderation review before becoming eligible for rewards.</p>
        <p style={bul}>• Ethio Telecom and SkykinTechnologies PLC reserve the right to remove any content that violates these Terms or applicable Ethiopian law without prior notice.</p>

        {/* 13 */}
        <div style={sec}>13. Acceptance of Terms and Modifications</div>
        <p style={bul}>• By subscribing to or using the FlipStar service, you confirm that you have read, understood, and agreed to these Terms and Conditions.</p>
        <p style={bul}>• Ethio Telecom reserves the right to cancel, amend, or modify these Terms and the service at any time. Any changes will be published at https://flipstar.et.</p>
        <p style={bul}>• By continuing to access or use the service after revised Terms become effective, you agree to be bound by the revised Terms. If you do not agree to the new Terms, you must stop using the service.</p>
        <p style={bul}>• These Terms shall remain in full force from the launch of the service until it is officially terminated, excluding temporary suspensions for operational reasons.</p>

        {/* 14 */}
        <div style={sec}>14. Participants and Disqualification</div>
        <p style={bul}>• Ethio Telecom reserves the right to disqualify any participant who appears to have breached any provision of these Terms.</p>
        <p style={bul}>• Customers participating in the service warrant that all information submitted is true, current, and complete.</p>
        <p style={bul}>• In the event of any dispute regarding these Terms, competition results, or any other matter relating to the service, the decision of Ethio Telecom shall be final.</p>

        {/* 15 */}
        <div style={sec}>15. Limitation of Liability</div>
        <p style={bul}>• Ethio Telecom accepts no responsibility for errors, omissions, interruptions, defects, delays in operation or transmission, or communications failures that are not within its direct control.</p>
        <p style={bul}>• Ethio Telecom is not responsible for problems or technical malfunctions of telephone networks, internet lines, computer systems, servers, or any combination thereof.</p>
        <p style={bul}>• Participants understand and agree that they participate in this service at their own risk and have not been coerced into participation.</p>
        <p style={bul}>• No claim relating to losses or injuries (including special, indirect, and consequential losses) shall be asserted against Ethio Telecom, SkykinTechnologies PLC, their parent companies, affiliates, directors, officers, employees, or agents.</p>

        {/* 16 */}
        <div style={sec}>16. Disclaimer of Warranties</div>
        <p style={bul}>• Ethio Telecom makes no warranty, implied or express, that any part of the FlipStar service will be uninterrupted and error-free.</p>
        <p style={bul}>• The service is provided on an 'as is' basis. Users accept that technical disruptions may occur.</p>

        {/* 17 */}
        <div style={sec}>17. Governing Law</div>
        <p style={para}>In the event of any disagreement arising from the use of this service, participants may present their complaint to Ethio Telecom. All disputes shall be resolved in accordance with the laws of the Federal Democratic Republic of Ethiopia (FDRE).</p>

        {/* 18 */}
        <div style={sec}>18. Contact Information</div>
        <TTable
          headers={["Channel", "Contact Detail"]}
          rows={[
            ["In-App Support", "Profile → Help & Support → Contact Us"],
            ["Email", "support@flipstar.et"],
            ["SMS", "8994"],
            ["Website", "https://www.ethiotelecom.et/"],
            ["Email (Ethio Telecom)", "994@ethionet.et"],
            ["WhatsApp", "+251 99 400 0000"],
            ["Telegram", "https://t.me/ethio_telecom"],
          ]}
        />
      </div>
    </div>
  );
}

export function ModernLoginScreen({ onSuccess, onRegister, onBack }) {
  const { colors: T } = useTheme();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [modal, setModal] = useState(null); // 'forgot' | 'faq' | 'terms'
  const [subscriptionOtpMode, setSubscriptionOtpMode] = useState(false);
  const [subPhone, setSubPhone] = useState("");
  const [subUsername, setSubUsername] = useState("");
  const [subOtp, setSubOtp] = useState("");
  const [subPassword, setSubPassword] = useState("");
  const [showSubPassword, setShowSubPassword] = useState(false);

  // Check URL params for subscription OTP mode and auto-detect login mode
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const hasSubscriptionParams = params.get('subscription_tp') === 'true' || params.get('subscriptiontp') === 'true';
    
    if (hasSubscriptionParams) {
      // Check if user is already logged in
      const storedUser = localStorage.getItem('user');
      if (storedUser) {
        // User already logged in, don't show subscription OTP mode
        setSubscriptionOtpMode(false);
        return;
      }
      
      // User not logged in, check if they have an account by checking phone number
      // Extract phone from URL if present
      const phoneFromUrl = params.get('phone');
      if (phoneFromUrl) {
        // Check if phone has an account
        checkPhoneHasAccount(phoneFromUrl);
      } else {
        // No phone in URL, show subscription OTP mode by default
        setSubscriptionOtpMode(true);
      }
    }
  }, []);

  const checkPhoneHasAccount = async (phone) => {
    try {
      const response = await api.post('/auth/check-phone-account/', { phone });
      if (response.data.has_account) {
        // Phone has account, show regular login
        setSubscriptionOtpMode(false);
        // Pre-fill phone number
        setEmail(phone);
      } else {
        // Phone doesn't have account, show subscription OTP mode
        setSubscriptionOtpMode(true);
        setSubPhone(phone);
      }
    } catch (e) {
      // On error, default to subscription OTP mode
      setSubscriptionOtpMode(true);
      setSubPhone(phone);
    }
  };

  const handleLogin = async (e) => {
    e?.preventDefault();
    
    if (!email || !password) {
      setError("Please fill in all fields");
      return;
    }
    
    setError("");
    setLoading(true);
    
    try {
      const username = email.includes("@") ? email.split("@")[0] : email;
      console.log('🔐 Attempting login for username:', username);
      const res = await api.login(username, password);
      
      console.log('✅ Login successful:', {
        userId: res.user.id,
        username: res.user.username,
        token: res.token ? res.token.substring(0, 10) + '...' : 'NONE'
      });
      
      api.setAuthToken(res.token);
      console.log('🔑 Token set via api.setAuthToken');
      
      // Include ALL user data from backend response (profile_photo, bio, etc.)
      const userData = {
        id: res.user.id,
        username: res.user.username,
        email: res.user.email,
        first_name: res.user.first_name || "",
        last_name: res.user.last_name || "",
        name: res.user.first_name || res.user.username,
        profile_photo: res.user.profile_photo || null,
        bio: res.user.bio || "",
        followers_count: res.user.followers_count || 0,
        following_count: res.user.following_count || 0,
        is_staff: res.user.is_staff || false,
      };
      
      console.log('👤 Calling onSuccess with user data:', userData);
      onSuccess(userData);
    } catch (e) {
      console.error('❌ Login error:', e);
      setError("Invalid credentials. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubscriptionOtpLogin = async (e) => {
    e?.preventDefault();
    
    if (!subPhone || !subUsername || !subOtp || !subPassword) {
      setError("Please fill in all fields");
      return;
    }
    
    if (!/^\d{6}$/.test(subPassword)) {
      setError("Password must be exactly 6 digits");
      return;
    }
    
    setError("");
    setLoading(true);
    
    try {
      const res = await api.post('/auth/login-with-subscription-otp/', {
        phone: subPhone,
        username: subUsername,
        otp: subOtp,
        password: subPassword
      });

      console.log('✅ Subscription OTP login response:', res);

      // API response is wrapped in { data } property
      const data = res.data || res;
      api.setAuthToken(data.token);

      const userData = {
        id: data.user.id,
        username: data.user.username,
        email: data.user.email,
        first_name: data.user.first_name || "",
        last_name: data.user.last_name || "",
        name: data.user.first_name || data.user.username,
        profile_photo: data.user.profile_photo || null,
        bio: data.user.bio || "",
        followers_count: data.user.followers_count || 0,
        following_count: data.user.following_count || 0,
        is_staff: data.user.is_staff || false,
      };

      console.log('✅ Calling onSuccess with userData:', userData);
      onSuccess(userData);
    } catch (e) {
      console.error('❌ Subscription OTP login error:', e);
      console.error('❌ Error response:', e?.response?.data);
      setError(e?.response?.data?.error || "Invalid OTP or subscription not found");
    } finally {
      setLoading(false);
    }
  };

  const inp = (focused) => ({
    width: "100%", padding: "13px 16px 13px 46px",
    background: T.cardBg || "#1A1A1A",
    border: `1.5px solid ${focused ? "#8fc441" : T.border || "#262626"}`,
    borderRadius: 10, fontSize: 15, color: T.txt || "#fff", outline: "none", boxSizing: "border-box",
  });

  return (
    <div style={{ minHeight: "100vh", background: T.bg || "#0D0D0D", display: "flex", alignItems: "center", justifyContent: "center", padding: "20px 16px" }}>
      {modal === "forgot" && <ForgotPasswordPhone onClose={() => setModal(null)} onSuccess={() => setModal(null)} />}
      {modal === "faq" && <FaqModal onClose={() => setModal(null)} />}
      {modal === "terms" && <TermsModal onClose={() => setModal(null)} />}

      <div style={{ width: "100%", maxWidth: 420 }}>
        {/* Logo Header */}
        <div style={{ 
          height: 90, 
          marginBottom: 24, 
          borderRadius: 12, 
          display: "flex", 
          flexDirection: "row",
          overflow: "hidden",
          position: "relative"
        }}>
<div style={{ width: "55%", backgroundColor: "#FFFFFF", height: "100%", position: "absolute", left: 0, top: 0 }}></div>
          <div style={{ width: "45%", backgroundColor: "#000000", height: "100%", position: "absolute", right: 0, top: 0 }}></div>
          <img src="/assets/logoG.png" alt="Logo" style={{ width: 420, height: 90, objectFit: "contain", position: "relative", zIndex: 1 }} />
        </div>

        {/* Card */}
        <div style={{ background: T.cardBg || "#1A1A1A", borderRadius: 18, padding: "28px 24px", border: "1px solid #8fc44130" }}>
          <div style={{ textAlign: "center", marginBottom: 24 }}>
            <div style={{ fontSize: 26, fontWeight: 900, color: "#8fc441", marginBottom: 4 }}>
              {subscriptionOtpMode ? "Login to Your Account" : "Welcome"}
            </div>
            <div style={{ fontSize: 13, color: "#8fc441" }}>
              {subscriptionOtpMode ? "Log in with your subscription OTP" : "Log in to continue to FLIPSTAR"}
            </div>
          </div>

        {/* Form */}
        {subscriptionOtpMode ? (
          <form onSubmit={handleSubscriptionOtpLogin}>
            {error && (
              <div style={{ padding: "10px 14px", background: "#2D1010", border: "1px solid #EF4444", borderRadius: 8, color: "#EF4444", fontSize: 13, fontWeight: 600, marginBottom: 16 }}>
                ⚠️ {error}
              </div>
            )}

            {/* Phone field */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#8fc441", marginBottom: 6, letterSpacing: 0.5 }}>Phone Number</label>
              <div style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#8fc441", display: "flex" }}><User size={17} /></div>
                <input type="tel" value={subPhone} onChange={e => setSubPhone(e.target.value)}
                  placeholder="09XXXXXXXX"
                  style={inp(false)}
                  onFocus={e => e.target.style.border = "1.5px solid #8fc441"}
                  onBlur={e => e.target.style.border = "1.5px solid #262626"}
                />
              </div>
            </div>

            {/* Username field */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#8fc441", marginBottom: 6, letterSpacing: 0.5 }}>Username</label>
              <div style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#8fc441", display: "flex" }}><User size={17} /></div>
                <input type="text" value={subUsername} onChange={e => setSubUsername(e.target.value)}
                  placeholder="Choose a username"
                  style={inp(false)}
                  onFocus={e => e.target.style.border = "1.5px solid #8fc441"}
                  onBlur={e => e.target.style.border = "1.5px solid #262626"}
                />
              </div>
            </div>

            {/* OTP field */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#8fc441", marginBottom: 6, letterSpacing: 0.5 }}>Subscription OTP</label>
              <div style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#8fc441", display: "flex" }}><Lock size={17} /></div>
                <input type="text" inputMode="numeric" maxLength={6} value={subOtp} onChange={e => setSubOtp(e.target.value)}
                  placeholder="Enter OTP from SMS"
                  style={inp(false)}
                  onFocus={e => e.target.style.border = "1.5px solid #8fc441"}
                  onBlur={e => e.target.style.border = "1.5px solid #262626"}
                />
              </div>
            </div>

            {/* New Password field */}
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#8fc441", marginBottom: 6, letterSpacing: 0.5 }}>New Password (6 digits)</label>
              <div style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#8fc441", display: "flex" }}><Lock size={17} /></div>
                <input
                  type={showSubPassword ? "text" : "password"}
                  inputMode="numeric" maxLength={6}
                  value={subPassword} onChange={e => setSubPassword(e.target.value)}
                  placeholder="••••••"
                  style={{ ...inp(false), paddingRight: 46 }}
                  onFocus={e => e.target.style.border = "1.5px solid #8fc441"}
                  onBlur={e => e.target.style.border = "1.5px solid #262626"}
                />
                <button type="button" onClick={() => setShowSubPassword(!showSubPassword)}
                  style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#8fc441" }}>
                  {showSubPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button type="submit" disabled={loading}
              style={{ width: "100%", padding: "14px", background: loading ? "#3A3A3A" : GOLD, border: "none", borderRadius: 10, color: loading ? "#888" : "#000", fontSize: 15, fontWeight: 800, cursor: loading ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginBottom: 16 }}>
              {loading ? <><Loader size={18} style={{ animation: "spin 1s linear infinite" }} /> Logging In…</> : "Login to Your Account"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleLogin}>
            {error && (
              <div style={{ padding: "10px 14px", background: "#2D1010", border: "1px solid #EF4444", borderRadius: 8, color: "#EF4444", fontSize: 13, fontWeight: 600, marginBottom: 16 }}>
                ⚠️ {error}
              </div>
            )}

            {/* Username field */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#8fc441", marginBottom: 7, letterSpacing: 0.5 }}>Username</label>
              <div style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#8fc441", display: "flex" }}><User size={17} /></div>
                <input type="text" value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="Enter your username"
                  style={inp(false)}
                  onFocus={e => e.target.style.border = "1.5px solid #8fc441"}
                  onBlur={e => e.target.style.border = "1.5px solid #262626"}
                />
              </div>
            </div>

            {/* Password field */}
            <div style={{ marginBottom: 8 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#8fc441", marginBottom: 7, letterSpacing: 0.5 }}>PIN</label>
              <div style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#8fc441", display: "flex" }}><Lock size={17} /></div>
                <input
                  type={showPassword ? "text" : "password"}
                  inputMode="numeric" maxLength={6}
                  value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••"
                  style={{ ...inp(false), paddingRight: 46 }}
                  onFocus={e => e.target.style.border = "1.5px solid #8fc441"}
                  onBlur={e => e.target.style.border = "1.5px solid #262626"}
                />
                <button type="button" onClick={() => setShowPassword(!showPassword)}
                  style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#8fc441" }}>
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button type="submit" disabled={loading}
              style={{ width: "100%", padding: "14px", background: loading ? "#3A3A3A" : GOLD, border: "none", borderRadius: 10, color: loading ? "#888" : "#000", fontSize: 15, fontWeight: 800, cursor: loading ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginBottom: 12 }}>
              {loading ? <><Loader size={18} style={{ animation: "spin 1s linear infinite" }} /> Logging in…</> : "Log In"}
            </button>

            {/* Forgot password */}
            <div style={{ textAlign: "center", marginBottom: 16 }}>
              <button type="button" onClick={() => setModal("forgot")}
                style={{ background: "none", border: "none", color: "#8fc441", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                Forgot password?
              </button>
            </div>
          </form>
        )}

          {/* Sign up */}
          <div style={{ textAlign: "center", fontSize: 13, color: "#666", marginBottom: 0 }}>
            Don't have an account?{" "}
            <button type="button" onClick={onRegister} style={{ background: "none", border: "none", color: "#8fc441", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>Subscribe</button>
          </div>
        </div>

        {/* Footer links - SUPER VISIBLE */}
        <div style={{ 
          display: "flex", 
          justifyContent: "center", 
          gap: 24, 
          marginTop: 40, 
          paddingBottom: 40, 
          borderTop: "3px solid #8fc441", 
          paddingTop: 30, 
          backgroundColor: "rgba(143,196,65,0.15)", 
          borderRadius: "12px",
          position: "relative",
          zIndex: 1000
        }}>
          <button 
            onClick={() => {
              console.log("FAQ button clicked!");
              alert("FAQ button clicked!");
              setModal("faq");
            }} 
            style={{ 
              background: "#8fc441", 
              border: "3px solid #fff", 
              color: "#000", 
              fontSize: 18, 
              cursor: "pointer", 
              fontWeight: 900, 
              padding: "16px 24px", 
              borderRadius: 12, 
              textDecoration: "none", 
              textUnderlineOffset: "0px",
              transition: "all 0.3s ease",
              boxShadow: "0 8px 24px rgba(143,196,65,0.4)",
              minHeight: "60px",
              minWidth: "150px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transform: "scale(1.1)",
              position: "relative",
              zIndex: 1001
            }}
            onMouseEnter={(e) => {
              e.target.style.background = "#6ba835";
              e.target.style.transform = "scale(1.15)";
              e.target.style.boxShadow = "0 12px 32px rgba(143,196,65,0.6)";
            }}
            onMouseLeave={(e) => {
              e.target.style.background = "#8fc441";
              e.target.style.transform = "scale(1.1)";
              e.target.style.boxShadow = "0 8px 24px rgba(143,196,65,0.4)";
            }}
          >
            📖 FAQ
          </button>
          <span style={{ 
            color: "#000", 
            fontSize: 20, 
            fontWeight: 800, 
            alignSelf: "center",
            background: "#fff",
            padding: "8px 12px",
            borderRadius: "50%"
          }}>•</span>
          <button 
            onClick={() => {
              console.log("Terms button clicked!");
              alert("Terms button clicked!");
              setModal("terms");
            }} 
            style={{ 
              background: "#8fc441", 
              border: "3px solid #fff", 
              color: "#000", 
              fontSize: 18, 
              cursor: "pointer", 
              fontWeight: 900, 
              padding: "16px 24px", 
              borderRadius: 12, 
              textDecoration: "none", 
              textUnderlineOffset: "0px",
              transition: "all 0.3s ease",
              boxShadow: "0 8px 24px rgba(143,196,65,0.4)",
              minHeight: "60px",
              minWidth: "150px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transform: "scale(1.1)",
              position: "relative",
              zIndex: 1001
            }}
            onMouseEnter={(e) => {
              e.target.style.background = "#6ba835";
              e.target.style.transform = "scale(1.15)";
              e.target.style.boxShadow = "0 12px 32px rgba(143,196,65,0.6)";
            }}
            onMouseLeave={(e) => {
              e.target.style.background = "#8fc441";
              e.target.style.transform = "scale(1.1)";
              e.target.style.boxShadow = "0 8px 24px rgba(143,196,65,0.4)";
            }}
          >
            📋 Terms & Conditions
          </button>
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}




