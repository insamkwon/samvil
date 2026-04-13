# Mobile Recipes — Expo / React Native Patterns

Reference patterns for building mobile apps with Expo Router + React Native + TypeScript + Zustand.

## Expo Router Layout Patterns

### Tab Navigation (default)

```typescript
// app/_layout.tsx — Root layout
import { Stack } from "expo-router";

export default function RootLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}

// app/(tabs)/_layout.tsx — Tab navigator
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: "#007AFF",
        tabBarStyle: { paddingBottom: 8, height: 60 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="home" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Settings",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="settings" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}
```

### Stack Navigation (detail screens)

```typescript
// app/(tabs)/index.tsx — Navigate to detail
import { router } from "expo-router";
import { TouchableOpacity, Text } from "react-native";

<TouchableOpacity onPress={() => router.push("/item/123")}>
  <Text>View Detail</Text>
</TouchableOpacity>

// app/item/[id].tsx — Detail screen
import { useLocalSearchParams, Stack } from "expo-router";

export default function ItemDetail() {
  const { id } = useLocalSearchParams();
  return (
    <>
      <Stack.Screen options={{ title: `Item ${id}`, headerShown: true }} />
      <Text>Item ID: {id}</Text>
    </>
  );
}
```

### Drawer Navigation

```typescript
// app/(drawer)/_layout.tsx
import { Drawer } from "expo-router/drawer";

export default function DrawerLayout() {
  return (
    <Drawer.Screen
      name="index"
      options={{ title: "Home", drawerLabel: "Home" }}
    />
  );
}
```

## React Native Component Patterns

### Basic Screen Component

```typescript
import { View, Text, StyleSheet, ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

export default function HomeScreen() {
  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <Text style={styles.title}>Welcome</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  scrollContent: { padding: 16 },
  title: { fontSize: 24, fontWeight: "bold", marginBottom: 16 },
});
```

### List with FlatList

```typescript
import { FlatList, Text, TouchableOpacity, StyleSheet } from "react-native";

interface Item {
  id: string;
  title: string;
}

function ItemList({ items, onPress }: { items: Item[]; onPress: (id: string) => void }) {
  return (
    <FlatList
      data={items}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => (
        <TouchableOpacity
          style={styles.item}
          onPress={() => onPress(item.id)}
        >
          <Text style={styles.itemTitle}>{item.title}</Text>
        </TouchableOpacity>
      )}
      ListEmptyComponent={
        <Text style={styles.empty}>No items yet. Add your first one!</Text>
      }
      contentContainerStyle={items.length === 0 ? styles.emptyList : undefined}
    />
  );
}

const styles = StyleSheet.create({
  item: {
    padding: 16,
    backgroundColor: "#fff",
    borderBottomWidth: 1,
    borderBottomColor: "#eee",
  },
  itemTitle: { fontSize: 16 },
  empty: { textAlign: "center", color: "#999", marginTop: 40 },
  emptyList: { flex: 1, justifyContent: "center" },
});
```

### Form Input

```typescript
import { View, TextInput, TouchableOpacity, Text, StyleSheet } from "react-native";

function AddItemForm({ onSubmit }: { onSubmit: (text: string) => void }) {
  const [text, setText] = useState("");

  return (
    <View style={styles.form}>
      <TextInput
        style={styles.input}
        value={text}
        onChangeText={setText}
        placeholder="Enter item name"
        placeholderTextColor="#999"
      />
      <TouchableOpacity
        style={styles.button}
        onPress={() => {
          if (text.trim()) {
            onSubmit(text.trim());
            setText("");
          }
        }}
      >
        <Text style={styles.buttonText}>Add</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  form: { flexDirection: "row", padding: 16, gap: 8 },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    paddingHorizontal: 12,
    height: 44,
    fontSize: 16,
  },
  button: {
    backgroundColor: "#007AFF",
    borderRadius: 8,
    paddingHorizontal: 16,
    height: 44,
    justifyContent: "center",
    minWidth: 80,
  },
  buttonText: { color: "#fff", fontWeight: "600", textAlign: "center" },
});
```

## Navigation Patterns

### Programmatic Navigation

```typescript
import { router } from "expo-router";

// Push to a route
router.push("/item/123");

// Go back
router.back();

// Replace current route
router.replace("/login");

// Navigate to tab
router.push("/(tabs)/settings");
```

### Passing Parameters

```typescript
// Navigate with params
router.push({ pathname: "/item/[id]", params: { id: "123" } });

// Read params in target screen
import { useLocalSearchParams } from "expo-router";
const { id } = useLocalSearchParams<{ id: string }>();
```

## Zustand State Management

### Store Creation

```typescript
// lib/store.ts
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import AsyncStorage from "@react-native-async-storage/async-storage";

interface Item {
  id: string;
  title: string;
  completed: boolean;
}

interface AppStore {
  items: Item[];
  addItem: (title: string) => void;
  toggleItem: (id: string) => void;
  removeItem: (id: string) => void;
}

export const useAppStore = create<AppStore>()(
  persist(
    (set) => ({
      items: [],
      addItem: (title) =>
        set((state) => ({
          items: [
            ...state.items,
            { id: Date.now().toString(), title, completed: false },
          ],
        })),
      toggleItem: (id) =>
        set((state) => ({
          items: state.items.map((item) =>
            item.id === id ? { ...item, completed: !item.completed } : item
          ),
        })),
      removeItem: (id) =>
        set((state) => ({
          items: state.items.filter((item) => item.id !== id),
        })),
    }),
    {
      name: "app-storage",
      storage: createJSONStorage(() => AsyncStorage),
    }
  )
);
```

### Using Store in Components

```typescript
import { useAppStore } from "@/lib/store";

function ItemList() {
  const items = useAppStore((s) => s.items);
  const toggleItem = useAppStore((s) => s.toggleItem);

  return (
    <FlatList
      data={items}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => (
        <TouchableOpacity onPress={() => toggleItem(item.id)}>
          <Text style={{ textDecorationLine: item.completed ? "line-through" : "none" }}>
            {item.title}
          </Text>
        </TouchableOpacity>
      )}
    />
  );
}
```

## Native Module Access

### Camera

```typescript
import { CameraView, CameraType, useCameraPermissions } from "expo-camera";
import { useState } from "react-native";

function CameraScreen() {
  const [facing, setFacing] = useState<CameraType>("back");
  const [permission, requestPermission] = useCameraPermissions();

  if (!permission?.granted) {
    return (
      <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
        <Button title="Grant Camera Permission" onPress={requestPermission} />
      </View>
    );
  }

  return (
    <CameraView style={{ flex: 1 }} facing={facing}>
      {/* Camera overlay UI */}
    </CameraView>
  );
}
```

### Location

```typescript
import * as Location from "expo-location";

async function getLocation() {
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== "granted") {
    alert("Location permission denied");
    return null;
  }
  const location = await Location.getCurrentPositionAsync({});
  return location.coords;
}
```

### Push Notifications

```typescript
import * as Notifications from "expo-notifications";

async function registerForPushNotifications() {
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== "granted") return null;
  const token = (await Notifications.getExpoPushTokenAsync()).data;
  return token;
}
```

## Platform-Specific Code

### Platform.select()

```typescript
import { Platform, StyleSheet } from "react-native";

const styles = StyleSheet.create({
  container: {
    paddingTop: Platform.select({ ios: 50, android: 25 }),
    ...Platform.select({
      ios: { shadowOpacity: 0.2, shadowRadius: 4, shadowOffset: { height: 2 } },
      android: { elevation: 4 },
    }),
  },
});
```

### Platform-specific files

```
Component.ios.tsx   — iOS-specific implementation
Component.android.tsx — Android-specific implementation
Component.tsx       — Shared fallback
```

## EAS Build Configuration

### eas.json

```json
{
  "cli": {
    "version": ">= 13.2.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal"
    },
    "preview": {
      "android": {
        "buildType": "apk"
      }
    },
    "production": {
      "autoIncrement": true
    }
  },
  "submit": {
    "production": {}
  }
}
```

### Build Commands

```bash
# Preview APK (for testing without store)
eas build --platform android --profile preview

# Production iOS
eas build --platform ios --profile production

# Production Android
eas build --platform android --profile production

# Submit to stores
eas submit --platform ios
eas submit --platform android

# OTA update
eas update --branch production --message "fix: bug description"
```

## Touch Target Guidelines

All interactive elements MUST have minimum 44x44 point touch targets:

```typescript
const styles = StyleSheet.create({
  button: {
    minHeight: 44,
    minWidth: 44,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 16,
  },
  iconButton: {
    width: 44,
    height: 44,
    justifyContent: "center",
    alignItems: "center",
  },
});
```
