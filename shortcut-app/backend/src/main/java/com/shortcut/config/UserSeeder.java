package com.shortcut.config;

import com.shortcut.domain.Role;
import com.shortcut.repository.UserRepository;
import java.util.List;
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
    private static final List<String> SEED_ADMINS = List.of("pd", "director");
    private static final List<SeedUser> USERS = List.of(
            new SeedUser("pd", "한서윤", Role.PRODUCER, "제작 PD (예산 권한자)", "010-7781-2045"),
            new SeedUser("manager", "오지훈", Role.PRODUCTION_MANAGER, "제작실장", "010-6620-3318"),
            new SeedUser("director", "강민재", Role.DIRECTOR, "연출 PD (연출감독)", "010-4473-9902"),
            new SeedUser("ad1", "윤하린", Role.AD1, "1조감독", "010-2219-5567"),
            new SeedUser("ad2", "서도현", Role.AD2, "2조감독", "010-8834-1206"),
            new SeedUser("dop", "문태오", Role.DOP, "촬영감독 (장비)", null),
            new SeedUser("sound", "배수아", Role.SOUND, "동시녹음팀장 (소음)", null),
            new SeedUser("crew", "임채원", Role.CREW, "연출부원 (열람만)", null));

    private final UserRepository users;
    private final PasswordEncoder passwordEncoder;

    public UserSeeder(UserRepository users, PasswordEncoder passwordEncoder) {
        this.users = users;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    public void run(String... args) {
        for (SeedUser seed : USERS) {
            if (!users.exists(seed.username())) {
                users.insertIfAbsent(seed.username(), passwordEncoder.encode(DEMO_PASSWORD), seed.name(), seed.role().name(),
                        seed.role().dept(), seed.title(), seed.phone());
            }
        }
        // 콜시트 수정 권한자(제작 PD, 연출 PD)를 처음 관리자로 둔다. 이후 권한은 관리자 페이지에서 바꾼다.
        users.grantAdminsIfNone(SEED_ADMINS);
    }

    private record SeedUser(String username, String name, Role role, String title, String phone) {
    }
}
