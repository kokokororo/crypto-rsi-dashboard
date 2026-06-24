// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: deep-purple; icon-glyph: chart-line;

// ==========================================================
// [설정] 본인의 Supabase URL과 Anon KEY를 아래에 입력하세요.
// ==========================================================
const SUPABASE_URL = "https://your-project-id.supabase.co"
const SUPABASE_KEY = "your-anon-key-here"

// API 통신 헤더 정의 (캐시 방지 헤더 추가)
const headers = {
  "apikey": SUPABASE_KEY,
  "Authorization": "Bearer " + SUPABASE_KEY,
  "Content-Type": "application/json",
  "Cache-Control": "no-cache, no-store, must-revalidate",
  "Pragma": "no-cache",
  "Expires": "0"
}

// Supabase DB 비동기 데이터 패치 함수
async function fetchData() {
  try {
    // iOS 시스템(WebKit)의 강제 캐시를 무력화하기 위해 요청 헤더에 고유한 타임스탬프 값을 매번 동적으로 주입합니다.
    // Supabase API는 모르는 헤더(X-Cache-Buster)가 들어오면 에러를 내지 않고 무시합니다.
    let reqHeaders = Object.assign({}, headers)
    reqHeaders["X-Cache-Buster"] = "" + Date.now()
    
    // 1. 실시간 가격 및 RSI 정보 조회
    let statusReq = new Request(`${SUPABASE_URL}/rest/v1/current_status?select=*`)
    statusReq.headers = reqHeaders
    statusReq.method = "GET"
    let statusData = await statusReq.loadJSON()
    
    // 2. 가장 최근에 생성된 매매 신호 로그 1건 조회
    let signalReq = new Request(`${SUPABASE_URL}/rest/v1/signal_logs?select=*&order=created_at.desc&limit=1`)
    signalReq.headers = reqHeaders
    signalReq.method = "GET"
    let signalData = await signalReq.loadJSON()
    
    return { status: statusData, latestSignal: signalData[0] || null }
  } catch (e) {
    console.error(e)
    return null
  }
}

// RSI 게이지 바 문자열 도우미 함수 (총 8글자 크기)
function makeProgressBar(rsi, length = 8) {
  let filledCount = Math.round((rsi / 100) * length)
  filledCount = Math.max(0, Math.min(length, filledCount))
  let bar = ""
  for (let i = 0; i < length; i++) {
    bar += (i < filledCount) ? "■" : "□"
  }
  return bar
}

// 메인 로직 구동
let data = await fetchData()
let widget = await createWidget(data)

if (config.runsInWidget) {
  Script.setWidget(widget)
} else {
  // 앱 내에서 테스트 구동 시 Medium 크기 프리뷰 열기
  widget.presentMedium()
}
Script.complete()

// 위젯 디자인 구성 함수 (Medium 사이즈 전용)
async function createWidget(data) {
  let widget = new ListWidget()
  
  // 고급스러운 딥 다크 그라데이션 배경색 설정
  let startColor = new Color("#1e1e24")
  let endColor = new Color("#0d0d10")
  let gradient = new LinearGradient()
  gradient.colors = [startColor, endColor]
  gradient.locations = [0.0, 1.0]
  widget.backgroundGradient = gradient
  widget.setPadding(12, 16, 12, 16)
  
  if (!data || !data.status) {
    let errorTxt = widget.addText("⚠️ DB 연결 오류")
    errorTxt.textColor = Color.red()
    errorTxt.font = Font.boldSystemFont(15)
    return widget
  }
  
  let statusList = data.status
  let latestSignal = data.latestSignal
  
  // 1. 최근 신호 분석 (4시간 이내에 생성된 신호가 있으면 액티브로 판별)
  let hasActiveSignal = false
  if (latestSignal) {
    // SQLite/Supabase KST 날짜 텍스트를 Date 객체로 파싱
    let signalTime = new Date(latestSignal.created_at.replace(" ", "T"))
    let now = new Date()
    let diffMs = now - signalTime
    // 4시간봉 기준이므로 4시간(14,400,000ms) 이내의 신호면 강조
    if (diffMs > 0 && diffMs < 4 * 60 * 60 * 1000) {
      hasActiveSignal = true
    }
  }
  
  // 헤더 영역 (가로 스택)
  let topRow = widget.addStack()
  topRow.layoutHorizontally()
  
  let titleTxt = topRow.addText("📈 Crypto RSI Monitor")
  titleTxt.textColor = new Color("#8e9aaf")
  titleTxt.font = Font.boldSystemFont(11)
  
  topRow.addSpacer()
  
  if (hasActiveSignal) {
    // 액티브 신호 발생 시 우측 상단 뱃지 추가
    let action = latestSignal.action
    let badgeStack = topRow.addStack()
    badgeStack.cornerRadius = 6
    badgeStack.setPadding(2, 6, 2, 6)
    
    let coinName = latestSignal.symbol.split("/")[0]
    
    if (action.includes("BUY")) {
      badgeStack.backgroundColor = new Color("rgba(40, 167, 69, 0.25)")
      let badgeTxt = badgeStack.addText(`🟢 BUY: ${coinName}`)
      badgeTxt.textColor = new Color("#2ec4b6")
      badgeTxt.font = Font.boldSystemFont(10)
    } else if (action.includes("SELL")) {
      badgeStack.backgroundColor = new Color("rgba(220, 53, 69, 0.25)")
      let badgeTxt = badgeStack.addText(`🔴 SELL: ${coinName}`)
      badgeTxt.textColor = new Color("#e71d36")
      badgeTxt.font = Font.boldSystemFont(10)
    }
  } else {
    // 평상시 모니터링 녹색 점 표시
    let normalTxt = topRow.addText("● 24H ACTIVE")
    normalTxt.textColor = new Color("#4caf50")
    normalTxt.font = Font.boldSystemFont(9)
  }
  
  widget.addSpacer(8)
  
  // 2. 코인 카드 렌더링 영역 (좌우 분할)
  let mainStack = widget.addStack()
  mainStack.layoutHorizontally()
  
  let btc = statusList.find(r => r.symbol === "BTC/USDT")
  let eth = statusList.find(r => r.symbol === "ETH/USDT")
  
  // 좌측 카드 (Bitcoin)
  let btcStack = mainStack.addStack()
  btcStack.layoutVertically()
  buildCoinCard(btcStack, btc, "BTC")
  
  mainStack.addSpacer()
  
  // 중앙 종횡 분리선
  let separator = mainStack.addStack()
  separator.size = new Size(1, 56)
  separator.backgroundColor = new Color("rgba(255, 255, 255, 0.1)")
  
  mainStack.addSpacer()
  
  // 우측 카드 (Ethereum)
  let ethStack = mainStack.addStack()
  ethStack.layoutVertically()
  buildCoinCard(ethStack, eth, "ETH")
  
  widget.addSpacer(8)
  
  // 3. 하단 풋터 영역 (수신 시각 및 최근 신호 안내)
  let bottomRow = widget.addStack()
  bottomRow.layoutHorizontally()
  
  let timeStr = btc ? btc.last_updated.substring(11, 16) : "--:--"
  let footerTxt = bottomRow.addText(`최근 갱신 KST ${timeStr} (4H봉)`)
  footerTxt.textColor = new Color("#5c677d")
  footerTxt.font = Font.systemFont(8)
  
  if (latestSignal) {
    bottomRow.addSpacer()
    let sigTimeStr = latestSignal.created_at.substring(11, 16)
    let sigAction = latestSignal.action
    let sigCoin = latestSignal.symbol.split("/")[0]
    let sigTxt = bottomRow.addText(`최근 신호: ${sigCoin} ${sigAction} (${sigTimeStr})`)
    sigTxt.textColor = new Color("#a2a2ad")
    sigTxt.font = Font.systemFont(8)
  }
  
  return widget
}

// 각 코인 정보를 카드 안으로 그려넣는 함수
function buildCoinCard(stack, coinData, name) {
  let nameTxt = stack.addText(name)
  nameTxt.textColor = Color.white()
  nameTxt.font = Font.boldSystemFont(13)
  
  stack.addSpacer(2)
  
  if (!coinData) {
    let noneTxt = stack.addText("수집 대기 중")
    noneTxt.textColor = Color.gray()
    noneTxt.font = Font.systemFont(11)
    return
  }
  
  // 가격 포맷팅 ($60,000 등)
  let priceFormatted = coinData.price.toLocaleString('en-US', { 
    style: 'currency', 
    currency: 'USD', 
    minimumFractionDigits: 0, 
    maximumFractionDigits: 2 
  })
  
  let priceTxt = stack.addText(priceFormatted)
  priceTxt.textColor = new Color("#e2eafc")
  priceTxt.font = Font.mediumSystemFont(12)
  
  stack.addSpacer(4)
  
  // RSI(20) 값에 따른 색상 구분
  let rsi = coinData.rsi
  let rsiTxt = stack.addText(`RSI(20): ${rsi.toFixed(1)}`)
  rsiTxt.font = Font.boldSystemFont(11)
  
  if (rsi <= 25) {
    rsiTxt.textColor = new Color("#2ec4b6") // BUY 영역 (청록)
  } else if (rsi >= 70) {
    rsiTxt.textColor = new Color("#e71d36") // SELL 영역 (빨강)
  } else {
    rsiTxt.textColor = new Color("#a2a2ad") // 중립 영역 (회색)
  }
  
  // RSI 문자열 진행 게이지 추가 (가시성 확보)
  stack.addSpacer(2)
  let barTxt = stack.addText(makeProgressBar(rsi, 8))
  barTxt.font = Font.systemFont(7)
  
  if (rsi <= 25) {
    barTxt.textColor = new Color("rgba(46, 196, 182, 0.6)")
  } else if (rsi >= 70) {
    barTxt.textColor = new Color("rgba(231, 29, 54, 0.6)")
  } else {
    barTxt.textColor = new Color("rgba(255, 255, 255, 0.2)")
  }
}
