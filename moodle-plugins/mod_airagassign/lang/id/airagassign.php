<?php
// This file is part of Moodle - http://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// Moodle is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with Moodle.  If not, see <http://www.gnu.org/licenses/>.

/**
 * Language strings (Indonesian) for AI RAG Assignment module.
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

// General.
$string['modulename'] = 'Tugas AI RAG';
$string['modulenameplural'] = 'Tugas AI RAG';
$string['modulename_help'] = 'Modul Tugas AI RAG memungkinkan guru membuat tugas yang dinilai secara otomatis menggunakan AI dengan Retrieval-Augmented Generation (RAG). Mendukung dua mode: Mode Kuis (beberapa soal jawaban singkat) dan Mode Esai (satu jawaban esai). AI menggunakan materi pembelajaran yang telah diunggah sebelumnya sebagai basis pengetahuan untuk penilaian.';
$string['pluginname'] = 'Tugas AI RAG';
$string['pluginadministration'] = 'Administrasi Tugas AI RAG';
$string['airagassign:addinstance'] = 'Tambah Tugas AI RAG baru';
$string['airagassign:view'] = 'Lihat Tugas AI RAG';
$string['airagassign:submit'] = 'Kirim jawaban Tugas AI RAG';
$string['airagassign:grade'] = 'Nilai Tugas AI RAG';
$string['airagassign:manage'] = 'Kelola Tugas AI RAG';
$string['airagassign:viewallsubmissions'] = 'Lihat semua pengiriman siswa';

// Form fields.
$string['assignmentname'] = 'Nama tugas';
$string['assignmentname_help'] = 'Masukkan nama deskriptif untuk tugas AI RAG ini.';
$string['assignmentmode'] = 'Mode tugas';
$string['assignmentmode_help'] = 'Pilih jenis tugas: Mode Kuis menyajikan beberapa soal jawaban singkat, sedangkan Mode Esai membutuhkan satu jawaban esai.';
$string['mode_quiz'] = 'Kuis (Jawaban Singkat)';
$string['mode_essay'] = 'Esai';
$string['maximumgrade'] = 'Nilai maksimal';
$string['maximumgrade_help'] = 'Nilai maksimal yang dapat dicapai untuk tugas ini. Nilai minimum adalah 1. Total skor semua kriteria rubrik harus sama persis dengan nilai ini.';
$string['duedate'] = 'Batas waktu';
$string['duedate_help'] = 'Setelah tanggal ini, siswa tidak dapat lagi mengirim dan guru dapat menilai dengan AI.';
$string['opendate'] = 'Tanggal dibuka';
$string['opendate_help'] = 'Siswa tidak dapat mengirim sebelum tanggal ini. Biarkan dinonaktifkan agar pengiriman langsung tersedia setelah aktivitas dibuat.';
$string['opendate_before_duedate_error'] = 'Tanggal dibuka harus lebih awal dari batas waktu.';
$string['dateorder_hint'] = 'Peringatan: tanggal dibuka harus lebih awal dari batas waktu.';
$string['notavailableyet'] = 'Tugas ini belum tersedia. Akan dibuka pada {$a}.';
$string['opened'] = 'Sudah dibuka';
$string['allowlatesubmission'] = 'Izinkan pengiriman terlambat';

// Materials selection.
$string['materialsheader'] = 'Basis Pengetahuan RAG';
$string['selectmaterials'] = 'Pilih materi pembelajaran';
$string['selectmaterials_help'] = 'Pilih satu atau lebih aktivitas Materi AI RAG dari kursus ini. Materi yang telah diunggah akan digunakan sebagai basis pengetahuan AI untuk penilaian.';
$string['nomaterials'] = 'Tidak ditemukan aktivitas Materi AI RAG di kursus ini. Silakan tambahkan dan vektorisasi materi terlebih dahulu.';
$string['nomaterialsavailable'] = 'Tugas ini belum dapat menerima pengiriman karena belum ada materi yang selesai divektorisasi. Silakan hubungi pengajar Anda.';
$string['selectedmaterials'] = 'Materi yang dipilih untuk konteks RAG';

// Rubric.
$string['rubricheader'] = 'Rubrik penilaian';
$string['rubriccriteria'] = 'Kriteria rubrik';
$string['rubriccriteria_help'] = 'Tentukan kriteria penilaian. Setiap kriteria memiliki nama, deskripsi, dan skor maksimal. AI akan mengevaluasi pengiriman berdasarkan setiap kriteria.';
$string['criterionname'] = 'Nama kriteria';
$string['criteriondesc'] = 'Deskripsi';
$string['criterionmaxscore'] = 'Skor maks';
$string['addcriterion'] = 'Tambah kriteria';
$string['removecriterion'] = 'Hapus';
$string['defaultcriterion_relevance'] = 'Relevansi';
$string['defaultcriterion_relevance_desc'] = 'Seberapa baik jawaban membahas pertanyaan menggunakan materi pembelajaran yang relevan.';
$string['defaultcriterion_accuracy'] = 'Akurasi';
$string['defaultcriterion_accuracy_desc'] = 'Kebenaran fakta dan konsep berdasarkan materi pembelajaran.';
$string['defaultcriterion_completeness'] = 'Kelengkapan';
$string['defaultcriterion_completeness_desc'] = 'Ketelitian dan cakupan poin-poin penting dari materi.';

// Quiz mode questions.
$string['questionsheader'] = 'Pertanyaan';
$string['questions_help'] = 'Tambahkan pertanyaan untuk kuis. Setiap pertanyaan akan dinilai secara individual menggunakan kriteria rubrik.';
$string['questiontext'] = 'Pertanyaan {$a}';
$string['addquestion'] = 'Tambah pertanyaan';
$string['removequestion'] = 'Hapus pertanyaan';
$string['numquestions'] = 'Jumlah pertanyaan: {$a}';

// Essay mode.
$string['essayprompt'] = 'Prompt esai';
$string['essayprompt_help'] = 'Jelaskan tugas esai. Ini adalah pertanyaan/prompt yang akan dijawab oleh siswa.';
$string['minwords'] = 'Jumlah kata minimum';
$string['maxwords'] = 'Jumlah kata maksimum';

// Submission.
$string['youranswer'] = 'Jawaban Anda';
$string['youressay'] = 'Esai Anda';
$string['submitanswers'] = 'Kirim jawaban';
$string['submitessay'] = 'Kirim esai';
$string['confirmsubmit'] = 'Apakah Anda yakin ingin mengirim? Anda tidak dapat mengubah jawaban setelah pengiriman.';
$string['submissionsaved'] = 'Pengiriman Anda telah disimpan.';
$string['alreadysubmitted'] = 'Anda sudah mengirim tugas ini.';
$string['notallowedsinceclosed'] = 'Tugas ini sudah ditutup. Pengiriman tidak lagi diterima.';
$string['wordcount'] = 'Jumlah kata: {$a}';
$string['wordcountbelowmin'] = 'Esai Anda harus minimal {$a} kata.';
$string['wordcountabovemax'] = 'Esai Anda tidak boleh melebihi {$a} kata.';

// Grading.
$string['gradewithairag'] = 'Nilai dengan AI RAG';
$string['gradingall'] = 'Nilai semua pengiriman dengan AI RAG';
$string['gradesubmission'] = 'Nilai pengiriman ini';
$string['grading'] = 'Menilai...';
$string['status_grading_failed'] = 'Penilaian AI gagal';
$string['retrygrading'] = 'Ulangi penilaian AI';
$string['grading_requestid'] = 'ID permintaan';
$string['graded'] = 'Sudah dinilai';
$string['notgraded'] = 'Belum dinilai';
$string['gradingsuccess'] = 'Berhasil menilai pengiriman untuk {$a}.';
$string['gradingerror'] = 'Kesalahan menilai pengiriman untuk {$a->student}: {$a->error}';
$string['gradingcomplete'] = 'Penilaian AI selesai. {$a->success} dari {$a->total} pengiriman berhasil dinilai.';
$string['moodlerubric_not_configured'] = 'Rubrik Bawaan Moodle dipilih, tetapi kriteria rubrik aktif belum dikonfigurasi. Simpan tugas, buka Penilaian Lanjutan (Advanced grading), tentukan rubriknya, lalu jalankan penilaian AI kembali.';
$string['nogradablesubmissions'] = 'Tidak ada pengiriman untuk dinilai.';
$string['overrideduedate'] = 'Batas waktu belum lewat. Tetap nilai?';
$string['viewresult'] = 'Lihat hasil';
$string['resultsfor'] = 'Hasil Penilaian AI RAG untuk {$a}';
$string['overallscore'] = 'Skor keseluruhan';
$string['overallfeedback'] = 'Umpan balik keseluruhan';
$string['criteriascores'] = 'Skor per kriteria';
$string['criterion'] = 'Kriteria';
$string['autocalculated'] = 'Otomatis';
$string['autocalculated_hint'] = 'Nilai ini dihitung otomatis dari jumlah skor per soal dan tidak dapat diubah secara langsung.';
$string['citations'] = 'Kutipan dari materi pembelajaran';
$string['confidence'] = 'Keyakinan AI';
$string['retrieveddocs'] = 'Dokumen yang diambil';
$string['nosource'] = 'Sumber tidak tersedia';
$string['gradedby'] = 'Dinilai oleh AI RAG';
$string['gradedat'] = 'Dinilai pada';

// Status.
$string['status_open'] = 'Dibuka';
$string['status_closed'] = 'Ditutup';
$string['status_grading'] = 'Penilaian sedang berlangsung';
$string['submissionstatus'] = 'Status pengiriman';
$string['submitted'] = 'Sudah dikirim';
$string['notsubmitted'] = 'Belum dikirim';
$string['submittedcount'] = '{$a->submitted} dari {$a->total} siswa telah mengirim';

// Server.
$string['serverurl'] = 'URL Server RAG';
$string['serverurl_desc'] = 'URL server API RAG (contoh: http://127.0.0.1:8000)';
$string['apikey'] = 'API Key (Opsional)';
$string['apikey_desc'] = 'Token bearer opsional yang sesuai dengan API_AUTH_TOKEN di server API RAG.';
$string['servererror'] = 'Tidak dapat terhubung ke server RAG. Silakan periksa URL server di pengaturan plugin.';

// Privacy.
$string['privacy:metadata'] = 'Plugin Tugas AI RAG menyimpan pengiriman siswa dan nilai yang dihasilkan AI.';

// Misc.
$string['search:activity'] = 'Tugas AI RAG';
$string['indicator:cognitivedepth'] = 'Kedalaman kognitif Tugas AI RAG';
$string['indicator:cognitivedepth_help'] = 'Indikator kedalaman kognitif untuk Tugas AI RAG.';
$string['indicator:socialbreadth'] = 'Keluasan sosial Tugas AI RAG';
$string['indicator:socialbreadth_help'] = 'Indikator keluasan sosial untuk Tugas AI RAG.';
$string['backtoassignment'] = 'Kembali ke tugas';
$string['allsubmissions'] = 'Semua pengiriman';
$string['student'] = 'Siswa';
$string['submitteddate'] = 'Tanggal kirim';
$string['grade'] = 'Nilai';
$string['status'] = 'Status';
$string['actions'] = 'Aksi';
$string['question'] = 'Pertanyaan';
$string['answer'] = 'Jawaban';
$string['score'] = 'Skor';
$string['feedback'] = 'Umpan balik';
$string['nosubmissions'] = 'Belum ada pengiriman.';
$string['duedatepassed'] = 'Batas waktu telah lewat.';
$string['duedatenotpassed'] = 'Batas waktu: {$a}';
$string['timeremaining'] = 'Waktu tersisa: {$a}';
$string['description'] = 'Deskripsi';
$string['assignmentinfo'] = 'Informasi tugas';
$string['rubricinfo'] = 'Rubrik';

// String UX form baru.
$string['assignmentname_placeholder'] = 'cth. Bab 5 - Kuis Deployment Pipeline';
$string['maximumgrade_error'] = 'Nilai maksimal harus minimal 1.';
$string['selectmaterials_placeholder'] = '— Klik atau ketik untuk mencari dan memilih materi —';
$string['materials_hint'] = 'Semua materi yang dipilih harus selesai divektorisasi (✓ [vectorized]) sebelum penilaian AI dapat dijalankan. Tips: Anda bisa mencari nama materi langsung di kolom pencarian.';
$string['essayheader'] = 'Pengaturan Mode Esai';
$string['essayprompt_required_hint'] = 'Wajib diisi untuk mode Esai. Jelaskan secara jelas apa yang harus ditulis siswa — ini adalah soal/pertanyaan yang ditampilkan kepada siswa.';
$string['essayprompt_placeholder'] = 'cth. Tuliskan sebuah esai yang menjelaskan proses deployment pipeline, termasuk tahapan dari commit kode hingga deployment ke produksi. Gunakan konsep dari materi perkuliahan.';
$string['essayprompt_required'] = 'Prompt esai wajib diisi untuk mode esai.';
$string['minmaxwords_hint'] = 'Isi dengan 0 untuk menonaktifkan batas jumlah kata ini.';
$string['rubric_sumhint'] = 'Penting: Total skor semua kriteria HARUS sama dengan Nilai Maksimal.';
$string['rubric_required_hint'] = 'Minimal 1 kriteria harus diisi. Kolom bertanda (*) wajib diisi. Contoh: jika Nilai Maksimal = 100, isi skor 40 + 35 + 25 = 100.';
$string['criterionname_placeholder'] = 'cth. Relevansi';
$string['criteriondesc_placeholder'] = 'cth. Seberapa baik jawaban membahas topik menggunakan materi perkuliahan';
$string['rubric_score_mismatch'] = 'Total skor kriteria ({$a->sum}) tidak sama dengan Nilai Maksimal ({$a->max}). Sesuaikan skor kriteria agar totalnya menjadi {$a->max}.';
$string['criterion_required_error'] = 'Minimal satu kriteria rubrik harus diisi.';
$string['questions_required_hint'] = 'Tambahkan minimal 1 pertanyaan. Siswa akan menjawab setiap pertanyaan secara terpisah, dan AI akan menilai masing-masing. Pertanyaan diberi nomor secara otomatis.';
$string['questionlabel'] = 'Pertanyaan';
$string['question_placeholder'] = 'cth. Jelaskan apa itu deployment pipeline dan uraikan tahapan-tahapan utamanya.';
$string['questions_required_error'] = 'Minimal satu pertanyaan harus diisi untuk mode kuis.';

// ── Human-in-the-loop (HITL) grading strings ─────────────────────────────────
$string['hitl_info'] = 'Human-in-the-loop: AI hanya memberikan saran penilaian. Semua nilai akhir ditetapkan dan dikonfirmasi oleh guru.';
$string['reviewaisuggestion'] = 'Tinjau Saran AI';
$string['aisuggestion'] = 'Saran AI';
$string['aisuggested_grade'] = 'Nilai yang Disarankan AI';
$string['grademanually'] = 'Nilai Secara Manual';
$string['gradingform'] = 'Formulir Penilaian';
$string['grading_decision'] = 'Keputusan Penilaian';
$string['accept_ai_suggestion'] = 'Terima Saran AI';
$string['override_grade'] = 'Timpa dengan nilai saya sendiri';
$string['finalgrade'] = 'Nilai Akhir';
$string['confirmgrade'] = 'Konfirmasi Nilai';
$string['gradeaccepted'] = 'Saran AI diterima dan disimpan sebagai nilai akhir.';
$string['gradeoverridden'] = 'Nilai berhasil ditimpa dan disimpan.';
$string['savefinalgrade'] = 'Simpan Nilai';
$string['ai_suggestion_pending'] = 'Saran AI Menunggu Tinjauan';
$string['ai_suggestions_pending'] = '{$a} pengiriman memiliki saran AI yang menunggu tinjauan Anda.';
$string['aisuggestion_ready'] = 'Saran AI siap untuk {$a}. Silakan tinjau dan konfirmasi nilai.';
$string['aigrading_complete_review'] = 'Penilaian AI selesai. {$a->success} dari {$a->total} pengiriman siap untuk ditinjau.';
$string['aisuggestion_available'] = 'Saran AI sudah tersedia untuk pengiriman ini.';
$string['studentsubmission'] = 'Pengiriman Siswa';
$string['teacher_note'] = 'Catatan guru';
$string['teacher_note_internal'] = 'internal, tidak ditampilkan ke siswa';
$string['teacher_note_placeholder'] = 'Opsional: catatan untuk diri sendiri tentang keputusan penilaian ini...';
$string['perquestion_scores'] = 'Skor per pertanyaan';
$string['editgrade'] = 'Edit Nilai';
$string['gradedby_ai_confirmed'] = 'Saran AI diterima oleh guru';
$string['gradedby_teacher'] = 'Dinilai secara manual oleh guru';
$string['ai_original_suggestion'] = 'Lihat saran AI asli';
$string['teacher_override'] = 'Nilai Ditimpa Guru';

// Bulk accept-all.
$string['acceptall_ai']           = 'Terima Semua Saran AI';
$string['acceptall_ai_confirm_title'] = 'Konfirmasi: Terima Semua Saran AI';
$string['acceptall_ai_confirm_body']  = '<strong>Peringatan!</strong> Anda akan menerima <strong>{$a} saran AI</strong> sebagai nilai akhir <strong>sekaligus</strong>, tanpa meninjau satu per satu. Tindakan ini akan langsung memfinalisasi semua nilai tersebut ke buku nilai dan <strong>tidak dapat dibatalkan</strong>. Pastikan Anda telah memeriksa bahwa saran-saran AI tersebut sudah masuk akal sebelum melanjutkan.';
$string['acceptall_ai_confirm_check'] = 'Saya memahami konsekuensinya dan ingin menerima semua saran AI sekaligus.';
$string['acceptall_complete']     = 'Selesai! {$a->success} dari {$a->total} saran AI berhasil diterima sebagai nilai akhir.';
$string['acceptall_nothing']      = 'Tidak ada saran AI yang menunggu — tidak ada yang perlu diterima.';
$string['acceptall_confirmation_required'] = 'Konfirmasi wajib diberikan sebelum menerima semua saran AI.';
$string['grading_queued_single'] = 'Penilaian AI untuk {$a} telah masuk antrian. Anda bisa membuka halaman lain dan kembali nanti.';
$string['grading_queued_bulk'] = 'Penilaian AI untuk {$a} pengiriman telah masuk antrian. Anda bisa membuka halaman lain dan kembali nanti.';
$string['grading_processing_title'] = 'Penilaian AI sedang berlangsung';
$string['queue_navigate_away'] = 'Anda bisa membuka halaman lain dan kembali nanti.';

// Rubric source and manual file strings.
$string['rubricmode'] = 'Sumber rubrik';
$string['rubricmode_help'] = 'Pilih sumber rubrik. Rubrik Kustom memungkinkan Anda menentukan kriteria langsung di bawah. Rubrik Bawaan Moodle menggunakan rubrik penilaian lanjutan bawaan Moodle (dikonfigurasi melalui administrasi Nilai).';
$string['rubricmode_custom'] = 'Rubrik Kustom (Bawaan Aktivitas)';
$string['rubricmode_moodle'] = 'Rubrik Bawaan Moodle (Penilaian Lanjutan)';
$string['moodlerubric_info_text'] = 'Anda memilih Rubrik Bawaan Moodle. Setelah menyimpan tugas ini, silakan buka menu **Penilaian Lanjutan** (Advanced Grading) pada pengaturan aktivitas ini untuk menentukan atau memilih rubrik yang aktif.';
$string['manualfile'] = 'Berkas Acuan / Kunci Jawaban (Manual)';
$string['manualfile_help'] = 'Unggah berkas acuan manual (PDF, PPTX, DOCX, TXT), seperti kunci jawaban model atau buku panduan referensi, untuk digunakan secara khusus sebagai konteks tambahan dalam penilaian.';
$string['submissions'] = 'Pengiriman';
$string['submissions_help'] = 'Jawaban siswa dan konteks pengiriman';
$string['gradeitem:submissions'] = 'Pengiriman';
$string['knowledgebase_required_error'] = 'Setidaknya salah satu dari "Pilih materi pembelajaran" atau "Berkas Acuan / Kunci Jawaban (Manual)" harus diisi.';
$string['linkedmaterials_no_vectorized_files'] = 'Tidak ada berkas pada materi kuliah tertaut yang berhasil divektorisasi. Jalankan ulang vektorisasi materi, lalu ulangi penilaian.';
$string['linkedmaterials_not_ready'] = 'Materi kuliah tertaut belum siap untuk penilaian: {$a}. Tunggu materi yang masih dalam antrean atau sedang diproses hingga selesai, dan vektorisasi ulang atau lepaskan materi yang masih menunggu atau gagal, lalu ulangi penilaian.';
$string['manualfile_delete_failed'] = 'Vektor berkas acuan yang dihapus ({$a}) gagal dihapus dari server RAG. Berkas tetap tercantum pada daftar status dan penghapusan akan dicoba lagi saat penyimpanan berikutnya atau saat \'Vektorisasi ulang berkas acuan\'.';
$string['manualfile_delete_failed_final'] = 'Vektor berkas acuan {$a->files} gagal dihapus dari server RAG. Minta administrator menghapus vektor milik {$a->owner}.';
$string['manualfile_status_deleting'] = 'Penghapusan dari server RAG gagal';
$string['manualfile_not_ready'] = 'Berkas acuan manual belum siap untuk penilaian: {$a}. Tunggu berkas yang sedang antre atau diproses selesai, atau vektorisasi ulang berkas yang gagal, lalu coba nilai lagi.';
$string['manualfile_revectorize'] = 'Vektorisasi ulang berkas acuan';
$string['manualfile_revectorize_none'] = 'Tugas ini tidak memiliki berkas acuan manual untuk divektorisasi.';
$string['manualfile_revectorize_queued'] = 'Berkas acuan manual telah dimasukkan ke antrean vektorisasi dan akan diproses di latar belakang.';
$string['manualfile_status'] = 'Status berkas acuan';
$string['manualfile_status_completed'] = 'Tervektorisasi';
$string['manualfile_status_failed'] = 'Gagal';
$string['manualfile_status_pending'] = 'Menunggu vektorisasi';
$string['manualfile_status_processing'] = 'Sedang diproses';
$string['manualfile_status_queued'] = 'Dalam antrean vektorisasi';
$string['task_vectorize_manualfile'] = 'Vektorisasi berkas acuan Tugas AI RAG';
