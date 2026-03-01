<template>
  <q-page class="q-pa-md bg-dark text-white font-inter">
    <div class="row q-col-gutter-lg">
      <!-- Left Column: Environment Settings -->
      <div class="col-12 col-md-4">
        <q-card dark flat bordered class="bg-grey-10 border-subtle">
          <q-card-section>
            <div class="text-h6 text-weight-bold q-mb-md">Environment Settings</div>
            
            <q-input
              dark
              v-model="envObjective"
              type="textarea"
              label="Simulation Objective"
              placeholder="e.g. Discuss the intersection of AI and Climate tech."
              filled
              autogrow
              class="q-mb-md"
            />

            <div class="text-subtitle2 q-mb-sm">Global Active Tools</div>
            <div class="row q-col-gutter-sm">
              <q-checkbox dark v-model="envTools" val="execute_python" label="Python Execution" color="primary" />
              <q-checkbox dark v-model="envTools" val="read_file" label="Read File" color="primary" />
              <q-checkbox dark v-model="envTools" val="web_search" label="Web Search" color="primary" />
              <q-checkbox dark v-model="envTools" val="create_file" label="Create File" color="primary" />
            </div>
          </q-card-section>
        </q-card>
      </div>

      <!-- Right Column: Synths Configuration -->
      <div class="col-12 col-md-8">
        <div class="flex justify-between items-center q-mb-md">
          <div class="text-h6 text-weight-bold">Agents (Synths)</div>
          <q-btn color="primary" icon="add" label="Add Synth" @click="addSynth" unelevated rounded />
        </div>

        <div v-if="synths.length === 0" class="text-grey-5 q-mb-md text-center q-py-lg border-dashed">
          No synths added yet. Click "Add Synth" to begin.
        </div>

        <q-card dark flat bordered class="bg-grey-10 border-subtle q-mb-md relative-position" v-for="(synth, index) in synths" :key="index">
          <q-btn 
            round 
            flat 
            icon="close" 
            color="red-4" 
            size="sm" 
            class="absolute-top-right q-ma-xs z-top" 
            @click="removeSynth(index)" 
          />
          <q-card-section>
            <div class="row q-col-gutter-md">
              <div class="col-12 col-sm-4">
                <q-input dark filled v-model="synth.synth_id" label="Synth ID" placeholder="e.g. Alex-01" />
              </div>
              <div class="col-12 col-sm-8">
                <q-select 
                  dark 
                  filled 
                  multiple 
                  v-model="synth.allowed_connections" 
                  :options="availableConnections(synth)" 
                  label="Allowed Connections" 
                  use-chips 
                >
                  <template v-slot:no-option>
                    <q-item dark>
                      <q-item-section class="text-grey">No other synths available</q-item-section>
                    </q-item>
                  </template>
                </q-select>
              </div>
            </div>

            <div class="q-mt-md">
              <q-input
                dark
                v-model="synth.persona_prompt"
                type="textarea"
                filled
                autogrow
                label="Persona Prompt"
                placeholder="Describe the agent's background, tone, and goals..."
              />
            </div>

            <div class="q-mt-md">
              <div class="text-caption text-grey-5 q-mb-xs">Allowed Tools (Subset of Global Tools)</div>
              <q-select 
                dark 
                filled 
                multiple 
                v-model="synth.allowed_tools" 
                :options="envTools" 
                label="Select Tools" 
                use-chips 
                v-if="envTools.length !== 0"
              />
              <div v-else class="text-caption text-orange-4">
                Enable Global Tools in Environment Settings first.
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <!-- Fixed Bottom Action Bar -->
    <q-page-sticky position="bottom" :offset="[0, 18]">
      <q-btn 
        color="primary" 
        size="lg" 
        icon="rocket_launch" 
        label="Launch Simulation" 
        @click="launchSimulation" 
        unelevated 
        rounded
        class="shadow-4"
        no-caps
        :disable="synths.length === 0"
      />
    </q-page-sticky>
  </q-page>
</template>

<script setup lang="ts">
import { useQuasar } from 'quasar';
import { ref } from 'vue';
import { useRouter } from 'vue-router';

// --- Environment State ---
const envObjective = ref('');
const $q = useQuasar();
const router = useRouter();
const envTools = ref<string[]>(['execute_python']);

// --- Synth State ---
interface SynthConfig {
  synth_id: string;
  persona_prompt: string;
  allowed_connections: string[];
  allowed_tools: string[];
  model: string;
}

const synths = ref<SynthConfig[]>([]);

// --- Computed & Methods ---
const addSynth = () => {
  synths.value.push({
    synth_id: `Agent-${synths.value.length + 1}`,
    persona_prompt: '',
    allowed_connections: [],
    allowed_tools: [...envTools.value], // Default to inheriting env tools
    model: 'gpt-4o'
  });
};

const removeSynth = (index: number) => {
  if (index < 0 || index >= synths.value.length) {
    return;
  }
  const removedId = synths.value[index]?.synth_id;
  synths.value.splice(index, 1);
  
  // Cleanup connections targeting the removed synth
  synths.value.forEach(s => {
    s.allowed_connections = s.allowed_connections.filter(c => c !== removedId);
  });
};

// Returns all synth IDs EXCEPT the current synth's ID for connection dropdown
const availableConnections = (currentSynth: SynthConfig) => {
  return synths.value
    .map(s => s.synth_id)
    .filter(id => id !== currentSynth.synth_id && id.trim() !== '');
};

const launchSimulation = async () => {
  // Construct the payload mapping for the existing backend API
  const payload = {
    environment: {
      objective: envObjective.value || "Survive and interact.",
      active_tools: envTools.value,

    },
    synths: synths.value.map(s => ({
      synth_id: s.synth_id,
      persona_prompt: s.persona_prompt || "You are a helpful assistant.",
      allowed_connections: s.allowed_connections,
      allowed_tools: s.allowed_tools,
    })),
    bootstrap_synths: false, // Set to true if you want OpenAI bootstrap to run
    mock_mode: true // Mocks the LLM to avoid API key requirement for testing
  };

  console.log("=== LAUNCH PAYLOAD ===");
  console.log(JSON.stringify(payload, null, 2));
  
  try {
    const response = await fetch('http://127.0.0.1:8000/api/simulations', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
    
    if (!response.ok) {
      const errText = await response.text();
      alert(`Error launching simulation: ${errText}`);
      return;
    }
    
    const data = await response.json();
    console.log("Simulation created successfully:", data);
    $q.notify({
      type: 'positive',
      message: 'Simulation launched successfully!',
      timeout: 2000,
    });
    await router.push(`/simulation/${data.env_id}`);  
  } catch (error) {
    console.error("Failed to push to backend:", error);
    $q.notify({
      type: 'negative',
      message: 'Failed to launch simulation.',
      timeout: 2000,
    });
  }
};
</script>

<style scoped>
.border-subtle {
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.border-dashed {
  border: 2px dashed rgba(255, 255, 255, 0.2);
  border-radius: 8px;
}
</style>
