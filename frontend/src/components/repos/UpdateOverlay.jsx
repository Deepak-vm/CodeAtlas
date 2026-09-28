import React from 'react'
import SyncIcon from '@mui/icons-material/Sync'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked'

export default function UpdateOverlay({ isUpdating, targetRepo, step }) {
  if (!isUpdating) return null

  const steps = [
    `Stripping stale chunks for '${targetRepo}' from indexes`,
    `Git pull latest & AST parse python files`,
    `JinaAI re-embedding '${targetRepo}' (only this repo)`,
    `Append updated vectors to FAISS & BM25 indexes`,
  ]

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-surface border border-accent-line rounded-2xl w-full max-w-lg p-7 flex flex-col gap-5 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-accent-soft border border-accent-line text-accent flex items-center justify-center">
            <SyncIcon className="animate-spin-custom !w-5 !h-5" />
          </div>
          <div>
            <h3 className="text-[17px] font-bold text-text m-0">
              Updating {targetRepo}...
            </h3>
            <p className="font-mono text-[11.5px] text-text-dim m-0">
              In-place isolated re-indexing — other repos stay untouched
            </p>
          </div>
        </div>

        {/* PROGRESS STEPS LIST */}
        <div className="flex flex-col gap-3.5 bg-surface-2 border border-border-soft rounded-xl p-4">
          {steps.map((text, idx) => {
            const isDone = step > idx + 1
            const isCurrent = step === idx + 1

            return (
              <div key={idx} className="flex items-center gap-3 text-[13px]">
                {isDone ? (
                  <CheckCircleIcon sx={{ fontSize: 18, color: '#7FD8A6' }} />
                ) : isCurrent ? (
                  <div className="w-4.5 h-4.5 border-2 border-accent border-t-transparent rounded-full animate-spin-custom flex-none" />
                ) : (
                  <RadioButtonUncheckedIcon sx={{ fontSize: 18, color: 'var(--text-dim)' }} />
                )}
                <span
                  className={`font-mono text-[12px] ${
                    isDone
                      ? 'text-[#7FD8A6] font-medium'
                      : isCurrent
                      ? 'text-accent font-bold'
                      : 'text-text-dim'
                  }`}
                >
                  Step {idx + 1}: {text}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
