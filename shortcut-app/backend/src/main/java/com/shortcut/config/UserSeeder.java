package com.shortcut.config;

import com.shortcut.repository.UserRepository;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * BCrypt 해시는 실행마다 달라 data.sql에 고정할 수 없어서 기동 시 코드로 만든다.
 * 테이블을 만드는 api 프로세스에서만 돌린다.
 */
@Component
@Profile("api")
public class UserSeeder implements CommandLineRunner {

    private static final String DEMO_PASSWORD = "shortcut1234";
    private static final List<SeedUser> USERS = List.of(
            new SeedUser("pd", "한서윤", "PRODUCER", "PRODUCTION", "제작 PD (예산 권한자)", "010-7781-2045"),
            new SeedUser("manager", "오지훈", "PRODUCTION_MANAGER", "PRODUCTION", "제작실장", "010-6620-3318"),
            new SeedUser("director", "강민재", "DIRECTOR", "DIRECTING", "연출감독", "010-4473-9902"),
            new SeedUser("ad1", "윤하린", "AD1", "DIRECTING", "1조감독", "010-2219-5567"),
            new SeedUser("ad2", "서도현", "AD2", "DIRECTING", "2조감독", "010-8834-1206"),
            new SeedUser("dop", "문태오", "DOP", "TECH", "촬영감독 (장비)", null),
            new SeedUser("sound", "배수아", "SOUND", "TECH", "동시녹음팀장 (소음)", null),
            new SeedUser("crew", "임채원", "CREW", "DIRECTING", "연출부원 (열람만)", null));

    private final boolean v3;
    private final UserRepository users;
    private final PasswordEncoder passwordEncoder;

    public UserSeeder(UserRepository users, PasswordEncoder passwordEncoder, @Value("${shortcut.dataset:legacy}") String dataset) {
        this.v3 = "V3".equals(dataset);
        this.users = users;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    public void run(String... args) {
        Map<String, String> names = Map.of("pd", "문태오", "manager", "임수빈", "director", "오지훈", "ad1", "정하린", "ad2", "이서후", "dop", "최도현", "sound", "조시온", "crew", "백지안");
        for (SeedUser seed : USERS) {
            if (!users.exists(seed.username())) {
                users.insertIfAbsent(seed.username(), passwordEncoder.encode(DEMO_PASSWORD), v3 ? names.get(seed.username()) : seed.name(), seed.role(),
                        seed.dept(), v3 && seed.username().equals("dop") ? "장비 책임자" : seed.title(), v3 ? null : seed.phone());
            }
        }
    }

    private record SeedUser(String username, String name, String role, String dept, String title, String phone) {
    }
}
