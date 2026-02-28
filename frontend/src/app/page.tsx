"use client";

import AudioManager from "@/components/AudioManager";
import SessionControls from "@/components/SessionControls";
import TutorPanel from "@/components/TutorPanel";
import Whiteboard from "@/components/Whiteboard";

export default function HomePage() {
  return (
    <main className="flex h-screen w-screen overflow-hidden">
      {/* Left panel — AI avatar, voice status, transcript */}
      <aside className="flex w-80 flex-shrink-0 flex-col border-r border-gray-200 bg-white shadow-sm">
        <TutorPanel />
        <div className="border-t border-gray-200 p-3">
          <SessionControls />
        </div>
      </aside>

      {/* Right panel — whiteboard canvas */}
      <section className="relative flex-1 overflow-hidden">
        <Whiteboard />
      </section>

      {/* Hidden audio management component */}
      <AudioManager />
    </main>
  );
}
