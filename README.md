# FFMPEG Video Editor Bot 🎬

บอทสำหรับประมวลผลและตัดต่อวิดีโอ Shorts/Reels อัตโนมัติ (FastAPI + FFMPEG) โดยออกแบบมาสำหรับรันบน Render.com (หรือระบบ Docker-ready ทั่วไป) รับคำสั่งและรูปภาพ/เสียงจาก n8n เพื่อทำการสร้างสไลด์โชว์พร้อมเอฟเฟกต์ Ken Burns ซูมเข้า-ออก และอัปโหลดไฟล์วิดีโอที่ได้ขึ้นไปเก็บที่ Supabase Storage โดยตรง

---

## 🛠️ โครงสร้างการทำงาน
1. รับ API request (`POST /generate-video`) พร้อม URL ของเสียงพากย์ และ URL ของรูปภาพฉากต่าง ๆ
2. ดาวน์โหลดรูปภาพและไฟล์เสียงมาประมวลผลในโฟลเดอร์ชั่วคราว
3. วิเคราะห์ความยาวของเสียงพากย์เพื่อคำนวณแบ่งเวลาแต่ละฉากให้ตรงกับสคริปต์เสียง
4. สร้างวิดีโอโดยเพิ่ม **Ken Burns Effect** ค่อยๆ ซูมเข้า-ออก (สลับซูมเข้าและซูมออกในแต่ละฉากเพื่อให้ดูมีมิติ)
5. รวมภาพและเสียงพากย์เข้าด้วยกันเป็นไฟล์วิดีโอเดียว (.mp4)
6. อัปโหลดวิดีโอสำเร็จรูปกลับขึ้นไปที่ **Supabase Storage** (Bucket: `videos`)
7. อัปเดตข้อมูลลิงก์วิดีโอและสถานะในตาราง `videos` ของ Supabase เป็น `completed`

---

## ⚙️ Environment Variables (ตัวแปรสภาพแวดล้อมที่ต้องตั้งค่า)
ต้องทำการตั้งค่าตัวแปรเหล่านี้ทั้งบนเครื่องโลคอล (ไฟล์ `.env`) และบนแผงควบคุมของ Render:

```env
SUPABASE_URL=https://xxxxxxxxxxxxxxxxxxxx.supabase.co
SUPABASE_KEY=service_role_key_ของ_supabase (ใช้สำหรับอัปโหลดไฟล์/อัปเดต DB)
```

---

## 💻 วิธีการติดตั้งและรันบนเครื่อง Local

### 1. ลงโปรแกรม FFMPEG บนเครื่อง (สำหรับ macOS)
หากยังไม่มี FFMPEG ให้ติดตั้งผ่าน Homebrew:
```bash
brew install ffmpeg
```

### 2. สร้าง Virtual Environment และติดตั้ง dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. สร้างไฟล์ `.env`
คัดลอกตัวอย่างด้านบนแล้วนำ URL/API Key ของ Supabase ไปวางในไฟล์ `.env`

### 4. รันเซิร์ฟเวอร์ทดสอบ
```bash
uvicorn main:app --reload --port 8080
```
ระบบจะรันขึ้นมาที่ `http://localhost:8080` คุณสามารถเข้าไปดูเอกสาร API ได้ที่ `http://localhost:8080/docs`

---

## 🚀 วิธีการ Deploy ไปยัง Render.com (ฟรี 100%)

Render.com รองรับการรัน Docker Container ในแพ็กเกจฟรี ซึ่งเหมาะอย่างยิ่งกับโปรเจกต์นี้เพราะเราเขียน `Dockerfile` ติดตั้ง FFMPEG ไว้ล่วงหน้าแล้ว:

### ขั้นตอนที่ 1: นำโค้ดขึ้น GitHub
1. สร้าง New Repository บน GitHub ส่วนตัวของคุณ (ตั้งชื่อเช่น `ffmpeg-video-api`)
2. เชื่อมโยง Git ในเครื่องคุณแล้ว Push ขึ้น GitHub:
   ```bash
   git branch -m main
   git remote add origin <ลิงก์-github-repo-ของคุณ>
   git push -u origin main
   ```

### ขั้นตอนที่ 2: ตั้งค่า Web Service บน Render
1. ไปที่ [dashboard.render.com](https://dashboard.render.com) แล้วกด **New +** -> **Web Service**
2. เลือกเชื่อมต่อกับ **GitHub Repository** ที่คุณเพิ่งอัปโหลดขึ้นไป
3. ตั้งค่าบริการ:
   - **Name**: `ffmpeg-video-api`
   - **Environment / Runtime**: เลือก **Docker** (สำคัญมาก! ระบบจะสร้าง Container ตาม Dockerfile ของเราและติดตั้ง FFMPEG ให้อัตโนมัติ)
   - **Region**: เลือกที่ใกล้คุณที่สุด (เช่น Singapore หรือ Oregon)
   - **Instance Type**: **Free**
4. กดที่ปุ่ม **Advanced** ด้านล่างเพื่อเพิ่ม **Environment Variables**:
   - `SUPABASE_URL` = (ค่า URL ของคุณ)
   - `SUPABASE_KEY` = (ค่า Service Role API Key ของคุณ)
5. กดปุ่ม **Create Web Service**

รอระบบ Build และ Deploy สักครู่ (ประมาณ 3-5 นาที) เมื่อเสร็จสิ้น คุณจะได้ลิงก์ URL ที่ลงท้ายด้วย `.onrender.com` เพื่อนำไปใช้งานร่วมกับ n8n ได้ทันที! 🎉
