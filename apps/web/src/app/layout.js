export const metadata = {
  title: "EV SafeCharge",
  description: "충전 성공 가능성 기반 전기차 충전소 추천",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
