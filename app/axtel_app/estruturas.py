"""Mapas de memória compartilhada (layout C, alinhamento natural).

Assetto Corsa / ACC: páginas Local\\acpmf_* (strings em UTF-16).
AC EVO: páginas Local\\acevo_pmf_* (strings em UTF-8).
Só os campos que o Axtel usa estão descritos; o resto da página é ignorado.
"""
import ctypes as C

f = C.c_float
i32 = C.c_int32
u32 = C.c_uint32
u16 = C.c_uint16
i16 = C.c_int16
i8 = C.c_int8
u8 = C.c_uint8
u64 = C.c_uint64
b = C.c_bool


def txt16(n):
    return u16 * n


def txt8(n):
    return u8 * n


# ---------------- Assetto Corsa (1) e ACC ----------------
class FisicaAC(C.Structure):
    _fields_ = [
        ("packetId", i32), ("gas", f), ("brake", f), ("fuel", f), ("gear", i32),
        ("rpms", i32), ("steerAngle", f), ("speedKmh", f), ("velocity", f * 3),
        ("accG", f * 3), ("wheelSlip", f * 4), ("wheelLoad", f * 4),
        ("wheelsPressure", f * 4), ("wheelAngularSpeed", f * 4), ("tyreWear", f * 4),
        ("tyreDirtyLevel", f * 4), ("tyreCoreTemperature", f * 4), ("camberRAD", f * 4),
        ("suspensionTravel", f * 4), ("drs", f), ("tc", f), ("heading", f), ("pitch", f),
        ("roll", f), ("cgHeight", f), ("carDamage", f * 5), ("numberOfTyresOut", i32),
        ("pitLimiterOn", i32),
    ]


_graficos_base = [
    ("packetId", i32), ("status", i32), ("session", i32),
    ("currentTime", txt16(15)), ("lastTime", txt16(15)), ("bestTime", txt16(15)), ("split", txt16(15)),
    ("completedLaps", i32), ("position", i32), ("iCurrentTime", i32), ("iLastTime", i32),
    ("iBestTime", i32), ("sessionTimeLeft", f), ("distanceTraveled", f), ("isInPit", i32),
    ("currentSectorIndex", i32), ("lastSectorTime", i32), ("numberOfLaps", i32),
    ("tyreCompound", txt16(33)), ("replayTimeMultiplier", f), ("normalizedCarPosition", f),
]


class GraficosAC(C.Structure):
    _fields_ = _graficos_base + [("carCoordinates", f * 3)]


class GraficosACC(C.Structure):
    _fields_ = _graficos_base + [
        ("activeCars", i32), ("carCoordinates", (f * 3) * 60), ("carID", i32 * 60), ("playerCarID", i32),
    ]


class EstaticoAC(C.Structure):
    _fields_ = [
        ("smVersion", txt16(15)), ("acVersion", txt16(15)), ("numberOfSessions", i32), ("numCars", i32),
        ("carModel", txt16(33)), ("track", txt16(33)), ("playerName", txt16(33)),
        ("playerSurname", txt16(33)), ("playerNick", txt16(33)), ("sectorCount", i32),
    ]


# ---------------- AC EVO ----------------
class PneuEvo(C.Structure):
    _fields_ = [
        ("slip", f), ("lock", b), ("tyre_pressure", f), ("tyre_temperature_c", f),
        ("brake_temperature_c", f), ("brake_pressure", f), ("tyre_temperature_left", f),
        ("tyre_temperature_center", f), ("tyre_temperature_right", f),
        ("tyre_compound_front", txt8(33)), ("tyre_compound_rear", txt8(33)),
        ("tyre_normalized_pressure", f), ("tyre_normalized_temperature_left", f),
        ("tyre_normalized_temperature_center", f), ("tyre_normalized_temperature_right", f),
        ("brake_normalized_temperature", f), ("tyre_normalized_temperature_core", f),
        ("_pad", u8 * 128),
    ]


class DanoEvo(C.Structure):
    _fields_ = [(n, f) for n in ("front", "rear", "left", "right", "center", "slf", "srf", "slr", "srr")] + [("_pad", u8 * 92)]


class PitEvo(C.Structure):
    _fields_ = [(n, i8) for n in ("damage", "fuel", "lf", "rf", "lr", "rr")] + [("_pad", u8 * 58)]


class InstrumentosEvo(C.Structure):
    _fields_ = [
        ("main_light_stage", i8), ("special_light_stage", i8), ("cockpit_light_stage", i8), ("wiper_level", i8),
        ("rain_lights", b), ("direction_light_left", b), ("direction_light_right", b), ("flashing_lights", b),
        ("warning_lights", b), ("selected_display_index", i8), ("display_current_page_index", i8 * 16),
        ("are_headlights_visible", b), ("_pad", u8 * 101),
    ]


class EletronicaEvo(C.Structure):
    _fields_ = [
        ("tc_level", i8), ("tc_cut_level", i8), ("abs_level", i8), ("esc_level", i8), ("ebb_level", i8),
        ("brake_bias", f), ("engine_map_level", i8), ("turbo_level", f), ("ers_deployment_map", i8),
        ("ers_recharge_map", f), ("is_ers_heat_charging_on", b), ("is_ers_overtake_mode_on", b),
        ("is_drs_open", b), ("diff_power_level", i8), ("diff_coast_level", i8),
        ("front_bump_damper_level", i8), ("front_rebound_damper_level", i8),
        ("rear_bump_damper_level", i8), ("rear_rebound_damper_level", i8), ("is_ignition_on", b),
        ("is_pitlimiter_on", b), ("active_performance_mode", i8), ("_pad", u8 * 88),
    ]


class SessaoEvo(C.Structure):
    _fields_ = [
        ("phase_name", txt8(33)), ("time_left", txt8(15)), ("time_left_ms", i32), ("wait_time", txt8(15)),
        ("total_lap", i32), ("current_lap", i32), ("lights_on", i32), ("lights_mode", i32),
        ("lap_length_km", f), ("end_session_flag", i32), ("time_to_next_session", txt8(15)),
        ("disconnected_from_server", b), ("restart_season_enabled", b), ("ui_enable_drive", b),
        ("ui_enable_setup", b), ("is_ready_to_next_blinking", b), ("show_waiting_for_players", b),
        ("_pad", u8 * 143),
    ]


class TempoEvo(C.Structure):
    _fields_ = [
        ("current_laptime", txt8(15)), ("delta_current", txt8(15)), ("delta_current_p", i32),
        ("last_laptime", txt8(15)), ("delta_last", txt8(15)), ("delta_last_p", i32),
        ("best_laptime", txt8(15)), ("ideal_laptime", txt8(15)), ("total_time", txt8(15)),
        ("is_invalid", b), ("_pad", u8 * 138),
    ]


class AjudasEvo(C.Structure):
    _fields_ = [(n, u8) for n in ("auto_gear", "auto_blip", "auto_clutch", "auto_clutch_on_start",
                                  "manual_ignition_e_start", "auto_pit_limiter", "standing_start_assist")] + [
        ("auto_steer", f), ("arcade_stability_control", f), ("_pad", u8 * 48)]


class GraficosEvo(C.Structure):
    _fields_ = [
        ("packet_id", i32), ("status", i32), ("focused_car_id_a", u64), ("focused_car_id_b", u64),
        ("player_car_id_a", u64), ("player_car_id_b", u64), ("rpm", u16),
    ] + [(n, b) for n in (
        "is_rpm_limiter_on", "is_change_up_rpm", "is_change_down_rpm", "tc_active", "abs_active", "esc_active",
        "launch_active", "is_ignition_on", "is_engine_running", "kers_is_charging", "is_wrong_way",
        "is_drs_available", "battery_is_charging", "is_max_kj_per_lap_reached", "is_max_charge_kj_per_lap_reached")] + [
        ("display_speed_kmh", i16), ("display_speed_mph", i16), ("display_speed_ms", i16),
        ("pitspeeding_delta", f), ("gear_int", i16), ("rpm_percent", f), ("gas_percent", f),
        ("brake_percent", f), ("handbrake_percent", f), ("clutch_percent", f), ("steering_percent", f),
        ("ffb_strength", f), ("car_ffb_multiplier", f), ("water_temperature_percent", f),
        ("water_pressure_bar", f), ("fuel_pressure_bar", f), ("water_temperature_c", i8),
        ("air_temperature_c", i8), ("oil_temperature_c", f), ("oil_pressure_bar", f),
        ("exhaust_temperature_c", f), ("g_forces_x", f), ("g_forces_y", f), ("g_forces_z", f),
        ("turbo_boost", f), ("turbo_boost_level", f), ("turbo_boost_perc", f), ("steer_degrees", i32),
        ("current_km", f), ("total_km", u32), ("total_driving_time_s", u32), ("time_of_day_hours", i32),
        ("time_of_day_minutes", i32), ("time_of_day_seconds", i32), ("delta_time_ms", i32),
        ("current_lap_time_ms", i32), ("predicted_lap_time_ms", i32), ("fuel_liter_current_quantity", f),
        ("fuel_liter_current_quantity_percent", f), ("fuel_liter_per_km", f), ("km_per_fuel_liter", f),
        ("current_torque", f), ("current_bhp", i32),
        ("tyre_lf", PneuEvo), ("tyre_rf", PneuEvo), ("tyre_lr", PneuEvo), ("tyre_rr", PneuEvo),
        ("npos", f), ("kers_charge_perc", f), ("kers_current_perc", f), ("control_lock_time", f),
        ("car_damage", DanoEvo), ("car_location", i32), ("pit_info", PitEvo), ("fuel_liter_used", f),
        ("fuel_liter_per_lap", f), ("laps_possible_with_fuel", f), ("battery_temperature", f),
        ("battery_voltage", f), ("instantaneous_fuel_liter_per_km", f), ("instantaneous_km_per_fuel_liter", f),
        ("gear_rpm_window", f), ("instrumentation", InstrumentosEvo), ("instrumentation_min_limit", InstrumentosEvo),
        ("instrumentation_max_limit", InstrumentosEvo), ("electronics", EletronicaEvo),
        ("electronics_min_limit", EletronicaEvo), ("electronics_max_limit", EletronicaEvo),
        ("electronics_is_modifiable", EletronicaEvo), ("total_lap_count", i32), ("current_pos", u32),
        ("total_drivers", u32), ("last_laptime_ms", i32), ("best_laptime_ms", i32), ("flag", i32),
        ("global_flag", i32), ("max_gears", u32), ("engine_type", i32), ("has_kers", b), ("is_last_lap", b),
        ("performance_mode_name", txt8(33)), ("diff_coast_raw_value", f), ("diff_power_raw_value", f),
        ("race_cut_gained_time_ms", i32), ("distance_to_deadline", i32), ("race_cut_current_delta", f),
        ("session_state", SessaoEvo), ("timing_state", TempoEvo), ("player_ping", i32), ("player_latency", i32),
        ("player_cpu_usage", i32), ("player_cpu_usage_avg", i32), ("player_qos", i32), ("player_qos_avg", i32),
        ("player_fps", i32), ("player_fps_avg", i32), ("driver_name", txt8(33)), ("driver_surname", txt8(33)),
        ("car_model_name", txt8(33)), ("is_in_pit_box", b), ("is_in_pit_lane", b), ("is_valid_lap", b),
        ("car_coordinates", (f * 3) * 60), ("gap_ahead", f), ("gap_behind", f), ("active_cars", u8),
        ("fuel_per_lap", f), ("fuel_estimated_laps", f), ("assists_state", AjudasEvo), ("max_fuel", f),
        ("max_turbo_boost", f), ("use_single_compound", b), ("car_ids", (u64 * 2) * 60),
    ]


class EstaticoEvo(C.Structure):
    _fields_ = [
        ("sm_version", txt8(15)), ("ac_evo_version", txt8(15)), ("session", i32), ("session_name", txt8(33)),
        ("event_id", u8), ("session_id", u8), ("starting_grip", i32), ("starting_ambient_temperature_c", f),
        ("starting_ground_temperature_c", f), ("is_static_weather", b), ("is_timed_race", b), ("is_online", b),
        ("number_of_sessions", i32), ("nation", txt8(33)), ("longitude", f), ("latitude", f),
        ("track", txt8(33)), ("track_configuration", txt8(33)), ("track_length_m", f),
    ]


TAMANHOS_EVO = {PneuEvo: 256, DanoEvo: 128, PitEvo: 64, InstrumentosEvo: 128, EletronicaEvo: 128,
                SessaoEvo: 256, TempoEvo: 256, AjudasEvo: 64}
for _s, _t in TAMANHOS_EVO.items():
    assert C.sizeof(_s) == _t, (_s.__name__, C.sizeof(_s))


def ctypes_sizeof(s):
    return C.sizeof(s)
