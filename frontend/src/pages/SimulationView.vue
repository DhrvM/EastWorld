<template>
    <q-layout view="hHh Lpr lff" container style="height: 100vh; border: 1px solid #333">
  <q-page-container>

  
  <q-page class="bg-dark text-white q-pa-md flex column no-wrap" style="height: calc(100vh - 50px)">
    <!-- Header: Simulation Stats -->
    <div class="row align-center justify-between q-mb-md border-subtle q-pa-sm rounded-borders">
      <div class="text-h6">Simulation ID: <span class="text-primary">{{ envId }}</span></div>
      
      <div class="row q-gutter-md items-center text-subtitle2">
        <div><q-icon name="sync" /> Round: {{ stats.rounds }}</div>
        <div><q-icon name="forum" /> Messages: {{ stats.messages }}</div>
        <div><q-icon name="build" /> Tool Calls: {{ stats.tool_calls }}</div>
      </div>
      <div>
        <q-btn 
          color="positive" 
          outline 
          icon="play_arrow" 
          :label="isAutoPlay ? 'Pause' : 'Auto Play'" 
          class="q-mr-sm" 
          @click="toggleAutoPlay" 
          :class="{ 'bg-positive text-white': isAutoPlay }"
        />
        <q-btn color="secondary" outline icon="skip_next" label="Next Round" class="q-mr-sm" @click="runOneRound" :disable="isAutoPlay" />
        <q-btn 
          outline 
          label="God Mode" 
          class="q-mr-sm" 
          @click="activeChat = 'GOD'" 
          :color="activeChat === 'GOD' ? 'primary' : 'primary'"
          :text-color="activeChat === 'GOD' ? 'white' : 'primary'"
        />
        <q-btn color="negative" outline label="End Demo" @click="goHome" />
      </div>
    </div>

    <!-- Main Grid: 3 Columns -->
    <div class="row flex-center q-col-gutter-md" style="flex: 1; min-height: 0;">
      
      <!-- Column 1: Configs & Synth Picker -->
      <div class="col-3 full-height flex column">
        <q-card class="bg-grey-10 full-height flex column border-subtle border-radius">
          <q-card-section class="bg-grey-9 q-py-sm">
             <div class="text-subtitle1 text-weight-bold">Objective</div>
          </q-card-section>
          <q-card-section class="q-py-sm text-caption text-grey-4 italic">
            "{{ objective }}"
          </q-card-section>
          <q-separator dark />
          <q-card-section class="bg-grey-9 q-py-sm row justify-between items-center">
            <div class="text-subtitle1 text-weight-bold">Active Synths</div>
            <q-badge color="primary">{{ synths.length }}</q-badge>
          </q-card-section>
          
          <q-scroll-area style="flex: 1;">
            <q-list dark separator class="q-pa-sm">
              <q-item 
                clickable v-ripple 
                v-for="s in synths" :key="s.synth_id"
                @click="activeChat = s.synth_id"
                :class="{ 'bg-primary': activeChat === s.synth_id }"
                class="rounded-borders q-mb-xs"
              >
                <q-item-section avatar>
                  <q-avatar color="grey-8" text-color="white">{{ s.name.charAt(0) }}</q-avatar>
                </q-item-section>
                <q-item-section>
                  <q-item-label>{{ s.name }}</q-item-label>
                  <q-item-label caption lines="1" class="text-grey-4">{{ s.persona_prompt }}</q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
          </q-scroll-area>
        </q-card>
      </div>

      <!-- Column 2: Direct Interaction Chat -->
      <div class="col-5 full-height flex column">
        <q-card class="bg-grey-10 full-height flex column border-subtle border-radius">
          <q-card-section class="bg-grey-9 q-py-sm row items-center justify-between">
            <div class="text-subtitle1 text-weight-bold">
              Interact: 
              <span class="text-primary">{{ activeChat === 'GOD' ? 'God System' : activeChatName }}</span>
            </div>
            <q-badge v-if="activeChat === 'GOD'" color="warning" text-color="black">Overview Analytics</q-badge>
            <q-badge v-else color="positive">Direct Message</q-badge>
          </q-card-section>
          
          <q-scroll-area style="flex: 1;" ref="chatScrollArea" class="q-pa-md">
             <q-chat-message
                v-for="(msg, index) in chatHistory[activeChat ? activeChat : 'GOD'] || []"
                :key="index"
                :name="msg.sender === 'user' ? 'You' : msg.name"
                :text="[msg.text]"
                :sent="msg.sender === 'user'"
                :bg-color="msg.sender === 'user' ? 'primary' : 'grey-8'"
                text-color="white"
              />
              <div v-show="isChatLoading" class="row justify-center q-my-sm">
                <q-spinner-dots color="primary" size="2em" />
              </div>
          </q-scroll-area>
          
          <q-separator dark />
          <q-card-section class="q-pa-sm bg-grey-9">
             <q-input
              v-model="chatInput"
              dark outlined dense
              :placeholder="activeChat === 'GOD' ? 'Ask a high-level question...' : `Message ${activeChatName}...`"
              @keyup.enter="sendMessage"
              :disable="!activeChat || isChatLoading"
            >
              <template v-slot:after>
                <q-btn round dense flat icon="send" color="primary" @click="sendMessage" :disable="!activeChat || isChatLoading || !chatInput.trim()" />
              </template>
            </q-input>
          </q-card-section>
        </q-card>
      </div>

      <!-- Column 3: Global Event Feed -->
      <div class="col-4 full-height flex column">
         <q-card class="bg-black full-height flex column border-subtle border-radius" style="border: 1px solid #333;">
          <q-card-section class="bg-grey-10 q-py-sm row justify-between items-center">
            <div class="text-subtitle1 text-weight-bold text-green-4"><q-icon name="terminal" /> Live Event Feed</div>
            <q-spinner-puff color="green-4" size="1.2em" />
          </q-card-section>
          <q-separator dark />
          
          <q-scroll-area style="flex: 1;" class="q-pa-sm font-mono text-caption" ref="feedScrollArea">
             <div v-for="(event, idx) in eventFeed" :key="idx" class="q-mb-xs">
                <span class="text-grey-6">[{{ formatTime(event.timestamp) }}]</span> 
                
                <span v-if="event.event_type === 'MESSAGE'" class="text-blue-3">
                  <span class="text-weight-bold">{{ event.sender }}</span>: {{ event.payload.text }}
                </span>
                
                <span v-else-if="event.event_type === 'TOOL_CALL'" class="text-orange-3">
                  ⚙️ <span class="text-weight-bold">{{ event.sender }}</span> called <span class="text-italic">{{ event.payload.tool }}</span>
                </span>
                
                <span v-else-if="event.event_type === 'TOOL_RESULT'" class="text-green-3">
                  ✅ <span class="text-weight-bold">{{ event.sender }}</span> got result
                </span>

                <span v-else-if="event.event_type === 'SYSTEM_ALERT'" class="text-red-3">
                  🚨 SYSTEM: {{ event.payload.message }}
                </span>
                
                <span v-else class="text-grey-4">
                  {{ event.sender }} - {{ event.event_type }}
                </span>
             </div>
          </q-scroll-area>
        </q-card>
      </div>
    </div>
  </q-page>
  </q-page-container>
</q-layout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue';
import type { Ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useQuasar } from 'quasar';
import type { QScrollArea } from 'quasar';

// --- Types ---
interface Synth {
  synth_id: string;
  name: string;
  persona_prompt: string;
  allowed_connections?: string[];
  allowed_tools?: string[];
}

interface EventData {
  text?: string;
  tool?: string;
  message?: string;
  [key: string]: string | number | boolean | object | null | undefined;
}

interface SimulationEvent {
  event_type: string;
  sender: string;
  timestamp?: string;
  payload: EventData;
}

const route = useRoute();
const router = useRouter();
const $q = useQuasar();

const envId = route.params.env_id as string;
const baseUrl = 'http://127.0.0.1:8000/api';

// State
const objective = ref('');
const synths = ref<Synth[]>([]);
const stats = ref({ rounds: 0, messages: 0, tool_calls: 0 });
const eventFeed = ref<SimulationEvent[]>([]);

// Chat Mode State
const activeChat = ref<string | null>(null);
const chatInput = ref('');
const isChatLoading = ref(false);
const chatHistory = ref<Record<string, {sender: string, name: string, text: string}[]>>({
  'GOD': []
});

const chatScrollArea = ref<QScrollArea | null>(null);
const feedScrollArea = ref<QScrollArea | null>(null);
let pollInterval: ReturnType<typeof setInterval> | null = null;
let eventSource: EventSource | null = null;

const isAutoPlay = ref(false);
let autoPlayInterval: ReturnType<typeof setInterval> | null = null;

const activeChatName = computed(() => {
  if (activeChat.value === 'GOD') return 'God System';
  const s = synths.value.find(s => s.synth_id === activeChat.value);
  return s ? s.name : 'Select a Synth';
});

// APIs
const fetchSimData = async () => {
  try {
    const res = await fetch(`${baseUrl}/simulations/${envId}`);
    if (!res.ok) throw new Error('Failed to load simulation');
    const data = await res.json();
    objective.value = data.objective;
    synths.value = data.synths;
    
    // Initialize chat history arrays for all synths
    data.synths.forEach((s: Synth) => {
      if (!chatHistory.value[s.synth_id]) {
        chatHistory.value[s.synth_id] = [];
      }
    });
    
    // Default open the first synth if god mode isn't active
    if (!activeChat.value && data.synths.length > 0) {
      activeChat.value = data.synths[0].synth_id;
    }
  } catch (error) {
    console.error(error);
    $q.notify({ type: 'negative', message: 'Failed to connect to Environment.' });
  }
};

const pollStats = async () => {
    console.log(eventFeed.value);
  try {
    const statsRes = await fetch(`${baseUrl}/simulations/${envId}/stats`);
    if (statsRes.ok) {
        stats.value = (await statsRes.json()).stats;
    }
  } catch (err) {
    console.warn("Stats polling error (might be offline)", err);
  }
};

const runOneRound = async () => {
  try {
    await fetch(`${baseUrl}/simulations/${envId}/rounds/one`, { method: 'POST' });
  } catch (error) {
    console.error("Failed to run round", error);
  }
};

const toggleAutoPlay = () => {
  isAutoPlay.value = !isAutoPlay.value;
  if (isAutoPlay.value) {
    autoPlayInterval = setInterval(() => {
      void runOneRound();
    }, 2500); // 2.5 seconds between rounds gives agents time to reply
  } else {
    if (autoPlayInterval) clearInterval(autoPlayInterval);
  }
};

const setupEventStream = () => {
  eventSource = new EventSource(`${baseUrl}/simulations/${envId}/stream`);
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.events && data.events.length > 0) {
        eventFeed.value.push(...data.events);
        scrollToBottom(feedScrollArea);
        // Refresh stats whenever a new event happens to keep the header perfectly in sync 
        void pollStats();
      }
    } catch (err) {
      console.error("Failed to parse SSE message", err);
    }
  };

  eventSource.onerror = (err) => {
    console.error("Event stream error, attempting to reconnect", err);
  };
};

const sendMessage = async () => {
  const text = chatInput.value.trim();
  const target = activeChat.value;
  if (!text || !target) return;
  
  chatInput.value = '';
  chatHistory.value[target]?.push({ sender: 'user', name: 'You', text });
  scrollToBottom(chatScrollArea);
  
  isChatLoading.value = true;
  
  try {
    let responseText = '';
    const responseName = activeChatName.value;
    
    if (target === 'GOD') {
      const res = await fetch(`${baseUrl}/simulations/${envId}/god`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text })
      });
      const data = await res.json();
      responseText = data.answer;
    } else {
      const res = await fetch(`${baseUrl}/simulations/${envId}/chat/${target}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      const data = await res.json();
      responseText = data.skip ? "[Skipped responding based on parameters]" : data.message;
    }
    
    chatHistory.value[target]?.push({ sender: 'agent', name: responseName, text: responseText });
    scrollToBottom(chatScrollArea);
  } catch (error) {
    console.error("Failed to send message:", error);
    $q.notify({ type: 'negative', message: 'Message failed to send.' });
    chatHistory.value[target]?.push({ sender: 'system', name: 'System', text: '[Network Error]' });
  } finally {
    isChatLoading.value = false;
  }
};

const goHome = async () => {
  await fetch(`${baseUrl}/simulations/${envId}/stop`, {
    method: 'POST',
  });
  await router.push('/');
};

const scrollToBottom = (refObj: Ref<QScrollArea | null>) => {
  nextTick().then(() => {
    if (refObj.value) {
      refObj.value.setScrollPosition('vertical', 99999, 300);
    }
  }).catch((err) => {
    console.error("Failed to scroll to bottom:", err);
  });
};

const formatTime = (isoString?: string) => {
  if (!isoString) return new Date().toLocaleTimeString();
  const date = new Date(isoString);
  return date.toLocaleTimeString([], { hour12: false });
};

// Lifecycle
onMounted(async () => {
  await fetchSimData();
  setupEventStream();
  
  // Intial stats fetch
  await pollStats();
  
  // We still poll stats infrequently just in case, but rely mainly on SSE updates
  pollInterval = setInterval(() => {
    void pollStats();
  }, 5000); 
});

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval);
  if (autoPlayInterval) clearInterval(autoPlayInterval);
  if (eventSource) eventSource.close();
});

</script>

<style scoped>
.border-subtle {
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.border-radius {
  border-radius: 8px;
}
.font-mono {
  font-family: 'Fira Code', 'Courier New', Courier, monospace;
}
</style>
