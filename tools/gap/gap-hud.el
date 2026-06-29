;;; gap-hud.el --- Live cockpit for the GAP agent council  -*- lexical-binding: t; -*-

;; Author: GAP
;; Keywords: games, tools
;; Package-Requires: ((emacs "27.1"))

;;; Commentary:

;; A live HUD for the DevilutionX GAP agent council, rendered in an Emacs
;; buffer.  It is deliberately NOT a new telemetry path: it renders the exact
;; same decision record that `decision_tracer.py' writes for replay/CI.  The
;; orchestrator's `LiveSink' (--hud PATH) overwrites a tiny JSON envelope every
;; tick; this package polls that file and draws it.
;;
;;   "This is not a dashboard bolted onto the AI.  It is the same decision
;;    artifact the tests replay, rendered live."
;;
;; Installation:
;;
;; This file lives in the DevilutionX repo (tools/gap/) on purpose — it renders
;; the orchestrator's decision record, so it should version lockstep with that
;; schema.  Don't copy it into your Emacs config; point at it where it lives.  It
;; is fully standalone (only built-ins: json, time-date, seq).
;;
;;   1. Try it, no config:
;;        M-x load-file RET .../DevilutionX/tools/gap/gap-hud.el RET
;;        M-x gap-hud
;;
;;   2. Adopt it permanently (straight.el + use-package):
;;        (use-package gap-hud
;;          :straight nil                                  ; local file, unmanaged
;;          :load-path "~/Projects/DevilutionX/tools/gap"
;;          :commands (gap-hud gap-hud-stop))
;;
;;      Or plain Emacs:
;;        (add-to-list 'load-path "~/Projects/DevilutionX/tools/gap")
;;        (autoload 'gap-hud "gap-hud" nil t)
;;
;; Usage:
;;   M-x gap-hud            ; watch ALL client feeds stacked (Airhead + Beavis…),
;;                          ; auto-discovered from .hud/ and re-scanned each tick
;;   C-u M-x gap-hud        ; focus a single client's feed (.hud/<hero>.json)
;;   M-x gap-hud-stop       ; stop polling
;;
;; Run the agent with the feed on:  HUD=1 ./launch_agent.sh
;;
;; The envelope shape (schema v2):
;;   {schema_version, source_id, written_at, offline, record:{...decision...}}

;;; Code:

(require 'json)
(require 'time-date)
(require 'seq)
(declare-function parse-iso8601-time-string "time-date" (string &optional zone))

(defgroup gap-hud nil
  "Live HUD for the GAP agent council."
  :group 'games)

;; Resolve the repo's .hud/ relative to THIS file so the default works no matter
;; where Emacs is when gap-hud loads (the .hud/ dir is a sibling of gap-hud.el in
;; tools/gap/).  Captured at load time; .elc and .el sit in the same directory.
(defconst gap-hud--dir
  (file-name-directory (or load-file-name buffer-file-name default-directory))
  "Directory this file was loaded from (tools/gap/ in the DevilutionX repo).")

(defcustom gap-hud-file
  (expand-file-name ".hud/multi_1.json" gap-hud--dir)
  "Default single feed, used when `gap-hud' is called with a prefix arg.
Each LiveSink writes one .hud/<hero>.json envelope; this is the fallback for
interactive single-feed selection.  By default `gap-hud' watches ALL feeds (see
`gap-hud-files'), so you rarely need this."
  :type 'file
  :group 'gap-hud)

(defcustom gap-hud-files nil
  "Feed files to watch, or nil to auto-discover every .hud/*.json.
nil (the default) shows every AI client's feed stacked in one buffer and picks
up newly-started clients automatically — fire up Beavis and he appears.  A list
of paths instead watches exactly those.  `gap-hud' with a prefix arg overrides
both with a single interactively-chosen feed."
  :type '(choice (const :tag "Auto-discover all" nil) (repeat file))
  :group 'gap-hud)

(defcustom gap-hud-interval 0.5
  "Seconds between HUD refreshes."
  :type 'number
  :group 'gap-hud)

(defcustom gap-hud-stale-seconds 3.0
  "Mark the feed STALE if the last write is older than this many seconds.
The orchestrator decides on a sub-second cadence, so a multi-second gap means
the agent is wedged, paused, or gone."
  :type 'number
  :group 'gap-hud)

(defcustom gap-hud-bar-width 10
  "Width, in block characters, of a full-score council bar."
  :type 'integer
  :group 'gap-hud)

;;;; Faces

(defface gap-hud-winner '((t :weight bold :foreground "gold"))
  "Face for the winning agent / command.")
(defface gap-hud-bar '((t :foreground "deep sky blue"))
  "Face for council score bars.")
(defface gap-hud-dim '((t :foreground "gray50"))
  "Face for secondary text (reasoning, plumbing).")
(defface gap-hud-label '((t :weight bold :foreground "white"))
  "Face for section labels.")
(defface gap-hud-ok '((t :foreground "spring green"))
  "Face for the live/online indicator.")
(defface gap-hud-warn '((t :weight bold :foreground "orange red"))
  "Face for stale/offline indicators.")

;;;; State

(defvar gap-hud--timer nil "Active refresh timer, or nil.")
(defvar gap-hud--buffer "*gap-hud*" "HUD buffer name.")
(defvar gap-hud--watching nil "Resolved list of feed files currently shown.")
(defvar gap-hud--auto nil
  "Non-nil when watching auto-discovered feeds (re-scanned each tick).")

;;;; Reading

(defun gap-hud--read-file (file)
  "Read and parse the envelope from FILE.
Return an alist, or nil if the file is missing or mid-write (atomic
`os.replace' on the writer means we normally never see a partial file)."
  (when (and file (file-readable-p file))
    (ignore-errors
      (with-temp-buffer
        (insert-file-contents file)
        (json-parse-buffer :object-type 'alist :array-type 'list
                           :null-object nil :false-object nil)))))

(defun gap-hud--age (env)
  "Seconds since ENV was written, or nil if unparseable."
  (let ((ts (alist-get 'written_at env)))
    (when ts
      (ignore-errors
        (float-time (time-subtract (current-time)
                                   (parse-iso8601-time-string ts)))))))

;;;; Rendering helpers

(defun gap-hud--ins (s &rest props)
  "Insert S, optionally propertized with PROPS."
  (insert (if props (apply #'propertize s props) s)))

(defun gap-hud--bar (score maxscore)
  "Return a block-char bar for SCORE relative to MAXSCORE."
  (let* ((frac (if (> maxscore 0) (/ (float score) maxscore) 0))
         (n (max 0 (min gap-hud-bar-width (round (* gap-hud-bar-width frac))))))
    (concat (make-string n ?█) (make-string (- gap-hud-bar-width n) ?·))))

(defun gap-hud--status-line (env age)
  "Insert the header status for ENV given its AGE in seconds."
  (let* ((offline (eq t (alist-get 'offline env)))
         (stale (and age (> age gap-hud-stale-seconds))))
    (cond
     (offline (gap-hud--ins "● OFFLINE" 'face 'gap-hud-warn))
     (stale   (gap-hud--ins (format "● STALE %.1fs" age) 'face 'gap-hud-warn))
     (t       (gap-hud--ins "● LIVE" 'face 'gap-hud-ok)))))

;;;; Rendering

(defun gap-hud--insert-feed (env file)
  "Insert one feed's panel at point in the current buffer.
ENV is the parsed envelope (or nil if FILE is unreadable/partial).  The caller
binds `inhibit-read-only' and manages the buffer; this only inserts at point —
it never erases — so several feeds stack in one buffer."
  (let ((rec (and env (alist-get 'record env)))
        (name (file-name-nondirectory file)))
    (cond
     ((null env)
      (gap-hud--ins (format "  %s — no data yet (agent running with HUD=1?)\n"
                            name) 'face 'gap-hud-dim))
     ((null rec)
      (gap-hud--ins (format "  %s — waiting for first decision …\n"
                            (or (alist-get 'source_id env) name)) 'face 'gap-hud-dim))
     (t
      (let* ((age (gap-hud--age env))
             (src (or (alist-get 'source_id env) "?"))
             (floor (alist-get 'floor rec))
             (tick (alist-get 'tick rec))
             (stance (or (alist-get 'tactical_mode rec) "follow"))
             (commit (alist-get 'commitment rec)))
        ;; Header: who / where / stance / commitment / status
        (gap-hud--ins (format "  %-10s" src) 'face 'gap-hud-winner)
        (gap-hud--ins (format "floor %s   tick %s   stance: %s"
                              floor tick (upcase stance)))
        (when commit
          (gap-hud--ins (format "   (committed: %s ×%s)"
                                (alist-get 'incumbent commit)
                                (alist-get 'streak commit))
                        'face 'gap-hud-dim))
        (insert "   ")
        (gap-hud--status-line env age)
        (insert "\n")
        (insert (make-string 70 ?─) "\n")
        ;; Council: each recommendation, score bar, reasoning. The killer panel.
        (let* ((recs (alist-get 'recommendations rec))
               (maxs (apply #'max 0.001
                            (mapcar (lambda (r) (or (alist-get 'score r) 0)) recs))))
          (gap-hud--ins "  COUNCIL\n" 'face 'gap-hud-label)
          (dolist (r (sort (copy-sequence recs)
                           (lambda (a b) (> (or (alist-get 'score a) 0)
                                            (or (alist-get 'score b) 0)))))
            (let ((agent (alist-get 'agent r))
                  (score (or (alist-get 'score r) 0))
                  (why (alist-get 'reasoning r)))
              (gap-hud--ins (format "   %-11s %5.1f  " agent score))
              (gap-hud--ins (gap-hud--bar score maxs) 'face 'gap-hud-bar)
              (when (and why (> (length why) 0))
                (gap-hud--ins (format "  %s" why) 'face 'gap-hud-dim))
              (insert "\n"))))
        ;; Winner + command + the "because"
        (let* ((winner (alist-get 'winner rec))
               (command (alist-get 'command rec))
               (recs (alist-get 'recommendations rec))
               (wrec (seq-find (lambda (r) (equal (alist-get 'agent r) winner)) recs))
               (why (and wrec (alist-get 'reasoning wrec))))
          (gap-hud--ins (format "  WINNER  %s → %s" winner command) 'face 'gap-hud-winner)
          (when (and why (> (length why) 0))
            (gap-hud--ins (format "      because: %s" why) 'face 'gap-hud-dim))
          (insert "\n"))
        (insert (make-string 70 ?─) "\n")
        ;; LLM plumbing: model / tokens / latency for each agent that called out.
        (let ((llm (alist-get 'llm rec)))
          (when llm
            (gap-hud--ins "  LLM\n" 'face 'gap-hud-label)
            (dolist (call llm)
              (let ((agent (alist-get 'agent call))
                    (model (alist-get 'model call))
                    (pt (alist-get 'prompt_tokens call))
                    (ot (alist-get 'out_tokens call))
                    (ms (alist-get 'latency_ms call))
                    (err (alist-get 'error call)))
                (gap-hud--ins (format "   %-11s %s" agent (or model "?")) 'face 'gap-hud-dim)
                (if err
                    (gap-hud--ins (format "   ⚠ %s" err) 'face 'gap-hud-warn)
                  (gap-hud--ins (format "   %s tok in / %s out · %s ms"
                                        (or pt "?") (or ot "?") (or ms "?"))
                                'face 'gap-hud-dim))
                (insert "\n"))))))))))

;;;; Tick

(defun gap-hud--tick ()
  "Poll every watched feed and redraw the buffer with feeds stacked."
  (let ((buf (get-buffer gap-hud--buffer)))
    (when buf
      ;; Auto mode: re-scan so a newly-started client (Beavis) just appears.
      (when gap-hud--auto
        (setq gap-hud--watching (or gap-hud-files (gap-hud--feeds))))
      (with-current-buffer buf
        (let ((inhibit-read-only t))
          (erase-buffer)
          (if (null gap-hud--watching)
              (gap-hud--ins
               "  no feeds yet — start an agent with HUD=1 (writes .hud/<hero>.json)\n"
               'face 'gap-hud-dim)
            (let ((first t))
              (dolist (file gap-hud--watching)
                (unless first (insert "\n"))   ; blank line between stacked feeds
                (setq first nil)
                (gap-hud--insert-feed (gap-hud--read-file file) file))))
          (goto-char (point-min)))))))

;;;; Commands

(defun gap-hud--feeds ()
  "Return existing .hud/*.json feed files in the repo's .hud/ dir."
  (let ((dir (expand-file-name ".hud/" gap-hud--dir)))
    (when (file-directory-p dir)
      (directory-files dir t "\\.json\\'"))))

(defun gap-hud--choose-feed ()
  "Prompt for a feed file, defaulting to the most recently written one."
  (let* ((feeds (sort (gap-hud--feeds)
                      (lambda (a b) (time-less-p (gap-hud--mtime b)
                                                 (gap-hud--mtime a))))))
    (if feeds
        (read-file-name "HUD feed: " (file-name-directory (car feeds))
                        (car feeds) t (file-name-nondirectory (car feeds)))
      (read-file-name "HUD feed: " gap-hud--dir gap-hud-file))))

(defun gap-hud--mtime (file)
  "Modification time of FILE."
  (file-attribute-modification-time (file-attributes file)))

;;;###autoload
(defun gap-hud (&optional arg)
  "Open the GAP cockpit and start polling the live feed(s).
By default watch ALL client feeds (`gap-hud-files', nil → auto-discover every
.hud/*.json), stacked in one buffer, re-scanned each tick so a newly-started
client just appears.  With prefix ARG, prompt for a single client's feed to
focus on instead."
  (interactive "P")
  (if arg
      (setq gap-hud--auto nil
            gap-hud--watching (list (gap-hud--choose-feed)))
    (setq gap-hud--auto (null gap-hud-files)
          gap-hud--watching (or gap-hud-files (gap-hud--feeds))))
  (with-current-buffer (get-buffer-create gap-hud--buffer)
    (gap-hud-mode))
  (gap-hud--tick)
  (when gap-hud--timer (cancel-timer gap-hud--timer))
  (setq gap-hud--timer (run-with-timer 0 gap-hud-interval #'gap-hud--tick))
  (display-buffer gap-hud--buffer)
  (message "GAP HUD watching %s"
           (if gap-hud--watching
               (mapconcat #'file-name-nondirectory gap-hud--watching ", ")
             "(no feeds yet — start an agent with HUD=1)")))

(defun gap-hud-stop ()
  "Stop polling the HUD file."
  (interactive)
  (when gap-hud--timer (cancel-timer gap-hud--timer) (setq gap-hud--timer nil))
  (message "GAP HUD stopped"))

(define-derived-mode gap-hud-mode special-mode "GAP-HUD"
  "Major mode for the live GAP agent cockpit."
  (buffer-disable-undo)
  (setq-local cursor-type nil)
  (setq truncate-lines t)
  (add-hook 'kill-buffer-hook #'gap-hud-stop nil t))

(provide 'gap-hud)
;;; gap-hud.el ends here
