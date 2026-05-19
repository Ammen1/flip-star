import { useState } from 'react';
import { X, ChevronDown, ChevronUp } from 'lucide-react';

const GOLD = '#8fc441';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

// ── FAQ DATA (mirrors mobile-app LoginScreen.js) ───────────────────────────
const FAQ_ITEMS = [
  { q: 'What is FlipStar?', a: "FlipStar is a premium, subscription-based gamified social media platform by Ethio telecom and Skykin Technologies PLC. Upload short videos and photos ('Flips'), compete in campaigns, earn coins, and participate in a creator economy powered by telebirr." },
  { q: 'Who can use FlipStar?', a: 'All active Ethio Telecom prepaid, postpaid, and hybrid mobile customers with a smartphone (Android, iOS) or web browser. Users must be at least 13 years old. For claiming prizes, users must be 18 or older.' },
  { q: 'What devices and platforms does FlipStar support?', a: 'Android App: Available on Google Play Store (search: FlipStar). iOS App: Available on Apple App Store (search: FlipStar). Web: Visit https://flipstar.et in any modern browser.' },
  { q: 'Is FlipStar available to all Ethio Telecom customers?', a: "Yes. All active prepaid, postpaid, and hybrid Ethio Telecom mobile customers can subscribe and use the service. The subscriber's number must be in 'Active' status at the time of subscription." },
  { q: 'How do I subscribe to FlipStar?', a: "Via SMS: Send 'OK1' (Daily), 'OK2' (Weekly), or 'OK3' (Monthly) to the FlipStar shortcode. Via App/Web: Download the app or visit https://flipstar.et, select 'Sign Up', enter your full name and mobile number, then enter the confirmation code sent to your number." },
  { q: 'What subscription plans are available?', a: 'Daily Plan: 3 ETB per day • Weekly Plan: 20 ETB per week • Monthly Plan: 70 ETB per month • Yearly Plan: 600 ETB per year • On-Demand: 10 ETB for 100 Coins (one-time purchase).' },
  { q: 'Is there a free trial?', a: 'Yes. New subscribers receive a 1-day (24-hour) free trial on their first subscription. Re-subscribers who previously used the trial are not eligible for another.' },
  { q: 'How am I charged?', a: 'Prepaid: fee deducted from airtime balance. Postpaid: fee added to monthly bill. Hybrid: charged from your default account. A maximum of one charge applies per 24-hour cycle. Failed charges are retried automatically if you recharge the same day.' },
  { q: 'How do I unsubscribe?', a: "Send 'STOP1' (Daily), 'STOP2' (Weekly), or 'STOP3' (Monthly) to the FlipStar shortcode, or go to Account Settings in the app and select Unsubscribe. Your request is processed immediately and you will receive a confirmation SMS." },
  { q: 'What happens to my coins and progress if I unsubscribe?', a: 'Your coins and digital assets remain valid for 30 days after unsubscription. Re-subscribing within 30 days restores your unexpired coins and progress. Assets not recovered within 30 days will expire.' },
  { q: 'What are coins and how do I earn them?', a: "Coins are FlipStar's digital currency. Earn them through: Daily login bonus (3 coins/day), Weekly loyalty bonus (50 coins for 7-day streak), Monthly bonus (200 coins for 30-day active streak), or Purchase via telebirr/Airtime." },
  { q: 'What can I do with coins?', a: 'Gift creators, boost your content visibility, unlock extended video uploads (up to 90-120 seconds), and unlock premium features.' },
  { q: 'Can I cash out my coins?', a: 'Bonus coins (from login/loyalty) cannot be cashed out. However, Points earned by creators from gifts can be cashed out via telebirr. Minimum: 1,000 Points (80 ETB after 20% commission).' },
  { q: 'What is the platform commission?', a: 'A 20% commission applies to all gifting transaction payouts. For example: if a creator earns 1,000 Points, 200 Points (20%) are retained as platform commission, and the creator receives 800 Points (80 ETB) via telebirr.' },
  { q: 'Can I convert my Points back into Coins?', a: 'Yes. The swap rate is 1 Point = 1 Coin. You can use earned Points to purchase more Coins for in-app spending instead of cashing out.' },
  { q: 'What is a Flip and how do I upload one?', a: "A Flip is a short video (15–120 seconds) or photo you upload to the platform. Tap the '+' button, select or record your content, add a caption and hashtags, optionally link it to a campaign, and tap 'Post'." },
  { q: 'How long can my videos be?', a: 'Standard subscribers: 15 to 60 seconds. Coin buyers (On-Demand / premium): up to 90–120 seconds.' },
  { q: 'What are the competition prizes?', a: 'Daily Sprint (50 winners): 1GB data • Weekly Battle (10 winners): 1,000 ETB • Monthly Star (5 winners): 10,000 ETB • Grand Final: 1st-500,000 ETB, 2nd-300,000 ETB, 3rd-200,000 ETB.' },
  { q: 'How is my competition score calculated?', a: 'Score = (Likes × 1) + (Comments × 2) + (Shares × 5) + (Gift/Vote Points × 10). The highest Engagement Score wins each tier.' },
  { q: 'Can I win multiple prizes?', a: "Yes, with rules. After winning a tier, you're ineligible for that same tier for 30 days. You can still win other tiers during the cooldown. Eligibility restores after 30 days." },
  { q: 'How do I claim my prize?', a: 'Cash prizes (ETB): sent automatically via telebirr. Daily Data prizes: credited to your Ethio Telecom account within 24 hours. Grand Final prizes: our team will contact you — you must present a valid National ID or passport. All prizes must be claimed within 30 days of notification.' },
  { q: 'Is there a daily voting limit for one creator?', a: "Yes. A single user can contribute a maximum of 5,000 Score Points (equivalent to 500 Coins) per day to any one specific creator. This Voting Cap prevents pay-to-win behaviour and protects competition integrity." },
  { q: 'Do boosted views count toward my leaderboard score?', a: 'No. Views and impressions from paid content boosts (Standard, Premium, or Viral Boost) do not count toward your organic Engagement Score. Only genuine, unboosted engagement contributes to your score.' },
  { q: 'Are there internet data charges for using FlipStar?', a: 'Yes. Accessing FlipStar via the app or web portal at https://flipstar.et uses your regular Ethio Telecom data plan. You are responsible for any data charges incurred.' },
  { q: 'Is my personal data safe?', a: 'Yes. FlipStar is hosted on Ethio Telecom InfraCloud within Ethiopia. Your phone number is encrypted and never displayed publicly. All personal metadata is removed from uploads.' },
  { q: 'Can Ethio Telecom change the Terms or cancel the service?', a: 'Yes. Ethio Telecom reserves the right to modify, suspend, or terminate the FlipStar service at any time in accordance with Ethiopian laws. Changes will be published at https://flipstar.et. Continued use after changes take effect constitutes acceptance.' },
  { q: 'How do I contact support?', a: 'In-App: Profile → Help & Support • Email: support@flipstar.et • SMS: 8994 • WhatsApp: +251 99 400 0000 • Telegram: t.me/ethio_telecom • Web: ethiotelecom.et' },
];

// ── Shared modal styles ────────────────────────────────────────────────────
const overlayStyle = {
  position: 'fixed', inset: 0,
  background: 'rgba(0,0,0,0.85)',
  zIndex: 5000,
  display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
  padding: 0,
  overflow: 'hidden',
};

const sheetStyle = {
  background: BG,
  width: '100%', maxWidth: 760,
  height: '100%',
  display: 'flex', flexDirection: 'column',
  borderLeft: `1px solid ${BORDER}`,
  borderRight: `1px solid ${BORDER}`,
};

const headerStyle = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '18px 20px',
  borderBottom: `1px solid ${BORDER}`,
  background: CARD,
};

const titleStyle = { fontSize: 18, fontWeight: 800, color: GOLD };
const closeBtnStyle = { background: 'none', border: 'none', cursor: 'pointer', color: GOLD, padding: 4, display: 'flex' };

// ── FAQ Modal ──────────────────────────────────────────────────────────────
export function FaqModal({ onClose }) {
  const [open, setOpen] = useState(null);
  return (
    <div style={overlayStyle} role="dialog" aria-modal="true">
      <div style={sheetStyle}>
        <div style={headerStyle}>
          <span style={titleStyle}>FAQ</span>
          <button onClick={onClose} style={closeBtnStyle} aria-label="Close"><X size={22} /></button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px 32px' }}>
          {FAQ_ITEMS.map((item, i) => {
            const isOpen = open === i;
            return (
              <div key={i} style={{ borderBottom: `1px solid ${BORDER}`, padding: '12px 0' }}>
                <button
                  onClick={() => setOpen(isOpen ? null : i)}
                  style={{
                    width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
                    color: '#fff', fontSize: 14, fontWeight: 600, padding: 0,
                  }}
                >
                  <span style={{ flex: 1, paddingRight: 12 }}>{item.q}</span>
                  {isOpen ? <ChevronUp size={16} color={GOLD} /> : <ChevronDown size={16} color={GOLD} />}
                </button>
                {isOpen && (
                  <div style={{ marginTop: 8, fontSize: 13, color: '#bbb', lineHeight: 1.6 }}>
                    {item.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Terms helpers ──────────────────────────────────────────────────────────
const ts = {
  para: { fontSize: 13, color: '#ccc', lineHeight: 1.65, marginBottom: 10 },
  sectionTitle: { fontSize: 16, fontWeight: 800, color: GOLD, marginTop: 20, marginBottom: 10 },
  subSectionTitle: { fontSize: 14, fontWeight: 700, color: '#fff', marginTop: 14, marginBottom: 8 },
  bullet: { fontSize: 13, color: '#ccc', lineHeight: 1.65, marginBottom: 6, paddingLeft: 4 },
  infoBox: { background: GOLD + '15', border: `1px solid ${GOLD}40`, borderRadius: 8, padding: 12, marginVertical: 10, marginTop: 10, marginBottom: 10 },
  infoText: { fontSize: 12, color: GOLD, fontWeight: 600, lineHeight: 1.5 },
  formulaBox: { background: CARD, border: `1px solid ${GOLD}`, borderRadius: 8, padding: 12, marginVertical: 10, marginTop: 10, marginBottom: 10 },
  formulaText: { fontSize: 12, color: GOLD, fontWeight: 700, textAlign: 'center' },
};

function TermsTable({ headers, rows, flex }) {
  const colFlex = flex || headers.map(() => 1);
  const cellBase = {
    padding: '8px 8px',
    fontSize: 11,
    color: '#ddd',
    borderRight: `1px solid ${BORDER}`,
    wordBreak: 'break-word',
  };
  return (
    <div style={{ border: `1px solid ${BORDER}`, borderRadius: 6, overflow: 'hidden', margin: '8px 0 14px', background: CARD }}>
      <div style={{ display: 'flex', background: '#222' }}>
        {headers.map((h, i) => (
          <div key={i} style={{ ...cellBase, flex: colFlex[i], color: GOLD, fontWeight: 700, fontSize: 11 }}>{h}</div>
        ))}
      </div>
      {rows.map((row, ri) => (
        <div key={ri} style={{ display: 'flex', background: ri % 2 === 1 ? '#141414' : 'transparent', borderTop: `1px solid ${BORDER}` }}>
          {row.map((cell, ci) => (
            <div key={ci} style={{ ...cellBase, flex: colFlex[ci] }}>{cell}</div>
          ))}
        </div>
      ))}
    </div>
  );
}

const P = ({ children }) => <p style={ts.para}>{children}</p>;
const S = ({ children }) => <h3 style={ts.sectionTitle}>{children}</h3>;
const SS = ({ children }) => <h4 style={ts.subSectionTitle}>{children}</h4>;
const B = ({ children }) => <p style={ts.bullet}>{children}</p>;
const Info = ({ children }) => (
  <div style={ts.infoBox}><span style={ts.infoText}>{children}</span></div>
);

// ── Terms Modal ────────────────────────────────────────────────────────────
export function TermsModal({ onClose }) {
  return (
    <div style={overlayStyle} role="dialog" aria-modal="true">
      <div style={sheetStyle}>
        <div style={headerStyle}>
          <span style={titleStyle}>Terms & Conditions</span>
          <button onClick={onClose} style={closeBtnStyle} aria-label="Close"><X size={22} /></button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px 40px' }}>

          <P>Please read these Terms and Conditions ("Terms") carefully before using the FlipStar service ("FlipStar", "the Service") provided by Ethio telecom and SkykinTechnologies PLC ("the Providers"). These Terms apply to all visitors, users, and others who access or use the Service via the FlipStar mobile application (Android and iOS) or web portal at https://flipstar.et.</P>
          <P>By subscribing, downloading, installing, or otherwise accessing FlipStar, you acknowledge that you have read, understood, and agree to be bound by these Terms. If you do not agree, do not use the Service.</P>

          <S>1. Introduction</S>
          <P>FlipStar is a premium, subscription-based gamified social media platform by Ethio telecom and Skykin Technologies PLC. Upload short videos and photos ('Flips'), compete in campaigns, earn coins, and participate in a creator economy powered by telebirr.</P>
          <P>FlipStar is accessible via:</P>
          <B>• Web Portal: https://flipstar.et</B>
          <B>• Android App: Available on Google Play Store (search: FlipStar)</B>
          <B>• iOS App: Available on Apple App Store (search: FlipStar)</B>

          <S>2. Service Overview</S>
          <B>• FlipStar is available to all active Ethio telecom prepaid, postpaid, and hybrid mobile customers with a smartphone (Android, iOS) or web browser.</B>
          <B>• The Service allows users to upload short-form videos (15–120 seconds depending on user tier) and photos, interact with content, participate in daily, weekly, monthly, and grand prize competitions, and earn and spend digital coins.</B>
          <B>• To subscribe via SMS: Send 'OK1' (Daily), 'OK2' (Weekly), or 'OK3' (Monthly) to the FlipStar shortcode. To unsubscribe: send 'STOP', 'STOP1', 'STOP2', or 'STOP3' to the same shortcode.</B>
          <B>• To subscribe via app or web: Download the FlipStar app or visit https://flipstar.et, select 'Sign Up', enter your full name and mobile number, then enter the confirmation code sent to your number.</B>

          <S>3. Subscription and Billing</S>
          <SS>3.1 Subscription Plans</SS>
          <TermsTable
            headers={['Plan', 'Price', 'Billing Cycle', 'Notes']}
            flex={[1.1, 0.9, 1, 1.5]}
            rows={[
              ['Flip Daily', '3 ETB', 'Every 24 hours', 'Charged daily. Auto-renewed while active.'],
              ['Flip Weekly', '20 ETB', 'Every 7 days', 'Charged weekly. Auto-renewed while active.'],
              ['Flip Monthly', '70 ETB', 'Every 30 days', 'Charged monthly. Auto-renewed while active.'],
              ['Flip On-Demand', '10 ETB / 100 Coins', 'One-time purchase', 'Coins purchased on demand. No recurring charge.'],
            ]}
          />
          <SS>3.2 SMS Subscription and Unsubscription Keywords</SS>
          <TermsTable
            headers={['Action', 'Accepted Keywords', 'Effect']}
            flex={[1, 1.5, 2]}
            rows={[
              ['Subscribe', 'OK1, OK2, OK3', 'Any of these keywords sent to the FlipStar shortcode will initiate a new subscription. All three keywords are equivalent and activate the same service.'],
              ['Unsubscribe', 'STOP1, STOP2, STOP3', 'Any of these keywords sent to the FlipStar shortcode will immediately cancel the active subscription. A confirmation SMS will be sent upon successful unsubscription.'],
            ]}
          />
          <Info>ⓘ SMS Keyword Note: All subscription and unsubscription keywords are case-insensitive (e.g. 'ok1' and 'OK1' are treated identically).</Info>
          <SS>3.3 Eligibility</SS>
          <B>• All active prepaid, postpaid, and hybrid Ethio telecom mobile customers are eligible to subscribe.</B>
          <B>• The subscriber's service number must be in 'Active' status at the time of subscription.</B>
          <B>• After any applicable free trial period, the subscriber must have sufficient balance to continue service.</B>
          <SS>3.4 Free Trial</SS>
          <B>• New subscribers receive a 1-day (24-hour) free trial on their first-time subscription.</B>
          <B>• The free trial is available for first-time subscribers only. Users who have previously subscribed and cancel are not eligible for a second free trial upon re-subscription.</B>
          <SS>3.5 Charging Logic</SS>
          <B>• Prepaid customers: Subscription fees are deducted from the current airtime balance.</B>
          <B>• Postpaid customers: Subscription fees are added to the monthly bill.</B>
          <B>• Hybrid customers: Fees are charged from the default account.</B>
          <B>• A maximum of one subscription charge per 24-hour cycle applies.</B>
          <B>• Failed billing attempts will be retried automatically per Ethio telecom Main Account (MA) time standards, or if the customer recharges their balance within the same day.</B>
          <B>• The service will be activated automatically after a successful subscription or payment.</B>
          <SS>3.6 Auto-Renewal</SS>
          <B>• FlipStar subscriptions auto-renew at the end of each billing cycle if the subscriber has sufficient balance.</B>
          <B>• Upon successful renewal, the subscriber will receive an SMS notification confirming the renewal and extended service period.</B>
          <B>• If auto-renewal fails due to insufficient balance, service access may be suspended until the next successful charge or manual resubscription.</B>
          <SS>3.7 Unsubscription</SS>
          <B>• To unsubscribe via SMS, send STOP1, STOP2, or STOP3 to the FlipStar shortcode. All three keywords have identical effect.</B>
          <B>• To unsubscribe via app or web: use the unsubscription option within the app or web portal under Account Settings.</B>
          <B>• Unsubscription requests are processed immediately.</B>
          <B>• A subscriber is considered active until they explicitly unsubscribe. Once cancelled, the user must re-subscribe to regain access to premium features.</B>
          <B>• Coins and digital assets earned or purchased prior to unsubscription remain valid for 30 days and are restored upon re-subscription within that period if not expired.</B>
          <Info>ⓘ SMS Notifications: You will receive an automatic SMS notification for: successful subscription, successful unsubscription, and each auto-renewal.</Info>

          <S>4. Accounts</S>
          <B>• Once you subscribe via SMS or complete registration via the app or web portal, FlipStar will automatically create an account using your Ethio telecom mobile number as your unique account identifier.</B>
          <B>• By accessing the service, you agree to be solely responsible for all activities that occur under your account and mobile number.</B>
          <B>• You agree to provide true, current, and complete information during registration and at all times during your use of the service.</B>
          <B>• Only one active account per mobile number is permitted.</B>

          <S>5. Digital Coins, Points, and the Creator Economy</S>
          <SS>5.1 Coins Overview</SS>
          <P>FlipStar operates a digital coin system that powers the platform's creator economy. Coins are the platform's internal currency used for content interaction, gifting, and access to premium features.</P>
          <TermsTable
            headers={['Action', 'Rate / Rule']}
            flex={[1, 2]}
            rows={[
              ['On-Demand Coin Pack', '10 ETB = 100 Coins (Flip On-Demand purchase).'],
              ['Daily login bonus', '3 Coins per day for opening the FlipStar app.'],
              ['Weekly loyalty bonus', '50 Coins bonus for consistent daily usage for a full week.'],
              ['Monthly loyalty bonus', '150 Coins bonus for consistent daily usage for a full month. Credited on the last day of the subscription month if all daily logins are recorded.'],
              ['Gift a creator', "Convert Coins into virtual Gifts sent to other users' content."],
              ['Creator earns Points', 'Creator receives 100% of the Gift Value as Points (1 Coin gifted = 1 Point earned).'],
              ['Cash out Points', '10 Points = 0.8 ETB (20% platform commission applied at payout).'],
              ['Re-invest Points', '1 Point = 1 Coin (swap earned Points back to Coins for in-app spending).'],
              ['Minimum cash-out threshold', '1,000 Points (equivalent to 80 ETB net after commission) required to trigger a telebirr payout.'],
            ]}
          />
          <SS>5.2 Gift Types and Point Values</SS>
          <TermsTable
            headers={['Gift Name', 'Cost per Unit (Coins)', 'Min Gift', 'Max Gift', 'Points to Creator', 'Max per Day']}
            flex={[1, 1.2, 1.2, 1.2, 1, 1.2]}
            rows={[
              ['Heart', '5 Coins', '5 Points (×1)', '250 Points (×50)', '1 Point per Coin', '500 Points'],
              ['Star', '20 Coins', '20 Points (×1)', '500 Points (×25)', '1 Point per Coin', '500 Points'],
              ['Crown', '50 Coins', '50 Points (×1)', '500 Points (×10)', '1 Point per Coin', '500 Points'],
              ['Rocket', '100 Coins', '100 Points (×1)', '1,000 Points (×10)', '1 Point per Coin', '2,000 Points'],
              ['Diamond', '500 Coins', '500 Points (×1)', '2,500 Points (×5)', '1 Point per Coin', '5,000 Points'],
              ['Galaxy', '1,000 Coins', '1,000 Points (×1)', '5,000 Points (×5)', '1 Point per Coin', '5,000 Points'],
            ]}
          />
          <Info>ⓘ Gift Daily Cap: A single user may contribute a combined maximum of 5,000 Score Points per day to any one specific creator across all gift types.</Info>
          <SS>5.4 Point Transfer Rules</SS>
          <TermsTable
            headers={['Transfer Rule', 'Limit', 'Applies To']}
            flex={[1.8, 1, 1.5]}
            rows={[
              ['Minimum points per transaction', '5 Points', 'Single gift or transfer action. Transactions below this threshold are rejected.'],
              ['Maximum points per transaction', '5,000 Points', 'Single gift or transfer action. Transactions above this threshold are split or rejected.'],
              ['Maximum points to one creator per day', '5,000 Points', 'Total points transferred to a single creator within a 24-hour rolling window (Voting Cap).'],
              ['Maximum total points sent per user per day', '10,000 Points', 'Total outbound points from one account across all recipients within a 24-hour rolling window.'],
              ['Maximum cash-out per request', '50,000 Points', 'Single telebirr withdrawal request. Larger balances require multiple separate withdrawal requests.'],
              ['Minimum cash-out threshold', '1,000 Points', 'Minimum balance required before a telebirr payout can be initiated (equivalent to 80 ETB net after 20% commission).'],
            ]}
          />
          <SS>5.5 Coin Rules</SS>
          <B>• Coins purchased via telebirr or Airtime have no expiry when actively used. Coins not used or converted within 30 days of purchase may expire.</B>
          <B>• Points not withdrawn or converted within 180 days of account inactivity are forfeited.</B>
          <B>• All coin purchases are non-refundable once processed.</B>
          <B>• Coins earned via daily bonuses and loyalty rewards (as opposed to purchased coins) may not be cashed out — they may only be spent within the platform (gifting, boosts, etc.).</B>
          <B>• A 20% platform commission is applied to all gifting transactions at the point of payout to a creator.</B>
          <B>• The minimum withdrawal threshold is 1,000 Points (net payout: 80 ETB). Payouts are processed via telebirr.</B>
          <SS>5.6 Content Boosting (Coin-Powered)</SS>
          <TermsTable
            headers={['Boost Type', 'Cost (Coins)', 'Effect', 'Leaderboard Impact']}
            flex={[1, 0.8, 1.4, 1.5]}
            rows={[
              ['Standard Boost', '100 Coins', "Featured in 'Trending' for 1 hour.", 'Boosted views do NOT count toward organic Leaderboard score.'],
              ['Premium Boost', '500 Coins', "Top of 'For You' feed for 6 hours.", 'Boosted views do NOT count toward organic Leaderboard score.'],
              ['Viral Boost', '1,000 Coins', '5,000 guaranteed impressions.', 'Boosted views do NOT count toward organic Leaderboard score.'],
            ]}
          />

          <S>6. Content and Upload Rules</S>
          <SS>6.1 Upload Limits</SS>
          <TermsTable
            headers={['User Type', 'Video Upload Limit', 'Access Method']}
            flex={[1.2, 0.9, 1.5]}
            rows={[
              ['Standard subscriber', '15 seconds – 60 seconds', 'Available to all active subscribers.'],
              ['Coin buyer (On-Demand / Premium)', 'Up to 90–120 seconds', 'Unlocked by purchasing coins or on-demand packs.'],
            ]}
          />
          <SS>6.2 User-Generated Content (UGC)</SS>
          <B>• By uploading content to FlipStar, you grant Ethio Telecom and SkykinTechnologies PLC a non-exclusive, royalty-free, worldwide licence to host, store, reproduce, and promote your content within and in connection with the FlipStar platform.</B>
          <B>• By participating in the service, you agree that your data (including name, initials, photos, and video images) may be used by Ethio Telecom for promotional and advertising purposes at no charge and without requiring prior individual consent.</B>
          <B>• All content uploaded for Weekly reward campaigns and above must pass AI and/or manual moderation for brand safety before becoming eligible for rewards.</B>
          <B>• All personal metadata (GPS location, device information) is automatically removed from all uploaded Flips before storage and publication.</B>
          <SS>6.3 Prohibited Content and Behaviour</SS>
          <B>• Users must not upload content that is unlawful, harmful, threatening, abusive, defamatory, or otherwise objectionable under Ethiopian law.</B>
          <B>• Botting, automated engagement, self-gifting, vote manipulation, or any attempt to artificially inflate scores or leaderboard rankings is strictly prohibited and results in immediate permanent account ban.</B>
          <B>• A single user may contribute a maximum of 5,000 Score Points (equivalent to 500 Coins) per day to any one specific creator ('Voting Cap'). This rule exists to prevent pay-to-win manipulation.</B>
          <B>• Ethio Telecom and SkykinTechnologies PLC reserve the right to disqualify any participant found to have breached these Terms and to ban any user who engages in inappropriate behaviour.</B>

          <S>7. Competitions and Rewards</S>
          <SS>7.1 The Engagement Score Formula</SS>
          <P>Your position on the competition leaderboard is determined by your Engagement Index, calculated as follows:</P>
          <div style={ts.formulaBox}>
            <span style={ts.formulaText}>Score = (Likes × 1) + (Comments × 2) + (Shares × 5) + (Gift/Vote Points × 10)</span>
          </div>
          <P>The user with the highest Engagement Score at the end of each competition period is declared the winner for that tier.</P>
          <SS>7.2 Competition Tiers and Prize Structure</SS>
          <TermsTable
            headers={['Competition Tier', 'Winner Count', 'Prize', 'Prize Delivery']}
            flex={[1.3, 0.8, 1.1, 1.5]}
            rows={[
              ['Daily Sprint', '50 winners', '1 GB Daily Data', 'Credited to telebirr/account within 24 hours.'],
              ['Weekly Battle', '10 winners', '1,000 ETB (via telebirr)', 'Sent via telebirr within 10 days of competition close.'],
              ['Monthly Star', '5 winners', '10,000 ETB (via telebirr)', 'Sent via telebirr within 10 days of competition close.'],
              ['Grand Final — 1st (Legend)', '1 winner', '500,000 ETB (via telebirr)', 'Sent via telebirr within 20 days of Grand Final campaign close.'],
              ['Grand Final — 2nd (Icon)', '1 winner', '300,000 ETB (via telebirr)', 'Sent via telebirr within 20 days of Grand Final campaign close.'],
              ['Grand Final — 3rd (Spark)', '1 winner', '200,000 ETB (via telebirr)', 'Sent via telebirr within 20 days of Grand Final campaign close.'],
            ]}
          />
          <SS>7.3 Winner Cooldown Rules</SS>
          <B>• Winners of a specific tier (Daily, Weekly, or Monthly) are ineligible to win that same tier again for 30 days from the date of winning.</B>
          <B>• During the 30-day cooldown, winners remain fully eligible to compete for all other tiers.</B>
          <B>• Eligibility for the same tier is automatically restored after 30 days.</B>
          <B>• A single user may win Daily, Weekly, and Monthly rewards within the same 30-day period, provided each win is in a different tier.</B>
          <B>• The Grand Final is a 6-month competition cycle. Grand Final winners (1st, 2nd, and 3rd place) are ineligible to compete for any Grand Final prize for a full 6 months from the date of their win.</B>
          <SS>7.4 Prize Redemption</SS>
          <B>• Cash prizes (ETB) will be sent via telebirr to the mobile number registered with the winning account.</B>
          <B>• Daily Data prizes are credited directly to the winner's Ethio Telecom account within 24 hours.</B>
          <B>• Grand Final and non-cash prize winners will be contacted by Ethio Telecom or SkykinTechnologies PLC representatives via the registered phone number.</B>
          <B>• All winners must present a valid identification document (National ID card or valid passport) to receive non-cash prizes.</B>
          <B>• Prizes may be received by an authorised representative of the winner upon written proxy confirmation from the winner, accompanied by valid identification of both parties.</B>
          <B>• Unclaimed prizes expire after 30 days from the date of notification. Expired prizes are awarded to the next eligible runner-up.</B>

          <S>8. Eligibility</S>
          <SS>8.1 Eligible Participants</SS>
          <B>• Individuals aged 13 years and above.</B>
          <B>• For prize collection: individuals aged 18 and above; minors under 18 must be accompanied by a parent or legal guardian to claim prizes.</B>
          <B>• Legal entities with duly authorised representatives.</B>
          <B>• All active Ethio Telecom prepaid, postpaid, and hybrid mobile customers.</B>
          <SS>8.2 Non-Eligible Participants</SS>
          <B>• Employees of Ethio Telecom and all directly associated partner organisations are not eligible to participate in prize competitions.</B>
          <B>• Any user found to have used automated tools (bots), multiple accounts, or any form of manipulation to influence competition results will be immediately and permanently disqualified and banned from the service.</B>

          <S>9. Data Usage Fees</S>
          <B>• Accessing FlipStar via https://flipstar.et or the mobile app uses your regular Ethio Telecom data plan.</B>
          <B>• You are solely responsible for any internet access or data charges incurred from your mobile carrier in connection with using the FlipStar service.</B>
          <B>• Ethio Telecom is not responsible for data charges incurred as a result of using the FlipStar service.</B>

          <S>10. Service Updates</S>
          <B>• For FlipStar to function properly, certain components may require updates from time to time. By accepting these Terms, you consent to the automatic installation of such updates.</B>
          <B>• During system updates, ongoing transactions, digital coins, earned points, and accumulated data remain unaffected.</B>
          <B>• Ethio Telecom reserves the right to temporarily suspend the service for operational reasons. The service will be restored as soon as reasonably possible following any temporary suspension.</B>

          <S>11. Inactivity Policy</S>
          <B>• Points not withdrawn or converted within 180 days of account inactivity are permanently forfeited.</B>
          <B>• Coins and tickets remain valid for up to 30 days for unsubscribed users and are restored upon re-subscription within that period, provided they have not expired.</B>
          <B>• Users are encouraged to log in daily to maintain activity and protect their earned assets.</B>

          <S>12. Content Moderation</S>
          <B>• FlipStar employs a hybrid AI and manual moderation system to review content for brand safety, legal compliance, and community standards.</B>
          <B>• All content submitted for Weekly competitions and above must successfully pass moderation review before becoming eligible for rewards.</B>
          <B>• Ethio Telecom and SkykinTechnologies PLC reserve the right to remove any content that violates these Terms or applicable Ethiopian law without prior notice.</B>

          <S>13. Acceptance of Terms and Modifications</S>
          <B>• By subscribing to or using the FlipStar service, you confirm that you have read, understood, and agreed to these Terms and Conditions.</B>
          <B>• Ethio Telecom reserves the right to cancel, amend, or modify these Terms and the service at any time. Any changes will be published at https://flipstar.et.</B>
          <B>• By continuing to access or use the service after revised Terms become effective, you agree to be bound by the revised Terms. If you do not agree to the new Terms, you must stop using the service.</B>
          <B>• These Terms shall remain in full force from the launch of the service until it is officially terminated, excluding temporary suspensions for operational reasons.</B>

          <S>14. Participants and Disqualification</S>
          <B>• Ethio Telecom reserves the right to disqualify any participant who appears to have breached any provision of these Terms.</B>
          <B>• Customers participating in the service warrant that all information submitted is true, current, and complete.</B>
          <B>• In the event of any dispute regarding these Terms, competition results, or any other matter relating to the service, the decision of Ethio Telecom shall be final.</B>

          <S>15. Limitation of Liability</S>
          <B>• Ethio Telecom accepts no responsibility for errors, omissions, interruptions, defects, delays in operation or transmission, or communications failures that are not within its direct control.</B>
          <B>• Ethio Telecom is not responsible for problems or technical malfunctions of telephone networks, internet lines, computer systems, servers, or any combination thereof.</B>
          <B>• Participants understand and agree that they participate in this service at their own risk and have not been coerced into participation.</B>
          <B>• No claim relating to losses or injuries (including special, indirect, and consequential losses) shall be asserted against Ethio Telecom, SkykinTechnologies PLC, their parent companies, affiliates, directors, officers, employees, or agents.</B>

          <S>16. Disclaimer of Warranties</S>
          <B>• Ethio Telecom makes no warranty, implied or express, that any part of the FlipStar service will be uninterrupted and error-free.</B>
          <B>• The service is provided on an 'as is' basis. Users accept that technical disruptions may occur.</B>

          <S>17. Governing Law</S>
          <P>In the event of any disagreement arising from the use of this service, participants may present their complaint to Ethio Telecom. All disputes shall be resolved in accordance with the laws of the Federal Democratic Republic of Ethiopia (FDRE).</P>

          <S>18. Contact Information</S>
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

          <div style={{ height: 40 }} />
        </div>
      </div>
    </div>
  );
}
